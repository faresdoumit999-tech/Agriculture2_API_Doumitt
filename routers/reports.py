"""Analytics and reports with Redis caching and rate limiting."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user, get_owned_project, is_admin, limiter
from config import settings
from database import get_db
from exceptions import BackgroundTaskError
from models import ExpenseRecord, Invoice, InvoiceItem, Project, User
from schemas import (
    CategoryBreakdown,
    CropBreakdown,
    CropHistoryPoint,
    CropHistoryResponse,
    ExpenseBreakdown,
    FullAuditReport,
    GlobalSummary,
    GlobalTotals,
    GreenhouseMetrics,
    NetProfitSummary,
    PesticideUsage,
    ProjectComparison,
    ProjectFinancialSummary,
    ProjectInfo,
    ProjectRead,
    ProjectWithSummary,
    SalesBreakdown,
    SharecropperStatement,
    TaskAccepted,
)
from services.currency_service import convert_invoice_amount, money
from services.sharecropper_service import invoice_syp_to_usd

logger = logging.getLogger("doumitt.reports")

router = APIRouter(prefix="/api", tags=["Reports & Analytics"])

CATEGORY_LABELS = {
    "POLYSTYRENE": "فلين",
    "VEHICLE_FUEL": "بنزين / مصاريف سيارة",
    "PESTICIDE": "أدوية زراعية",
    "FERTILIZER": "أسمدة",
    "SETUP": "تجهيز موسمي",
    "OTHER": "أخرى",
}


def report_cache_key(func, namespace, *, request=None, response=None, args=None, kwargs=None):
    """Per-user cache key so cached reports can never leak across tenants."""
    user = (kwargs or {}).get("current_user")
    user_id = getattr(user, "id", "anonymous")
    path = request.url.path if request is not None else func.__name__
    query = request.url.query if request is not None else ""
    return f"{namespace}:{func.__name__}:user:{user_id}:{path}?{query}"


def cached_report(expire: int):
    """Apply ``fastapi-cache2`` only when caching is enabled."""

    def decorator(func):
        if not settings.cache_enabled:
            return func
        return cache(expire=expire, namespace="reports", key_builder=report_cache_key)(func)

    return decorator


async def invalidate_reports_cache() -> None:
    """Flush every cached financial report after a mutation."""
    if not settings.cache_enabled:
        return
    try:
        await FastAPICache.clear(namespace="reports")
    except Exception:  # pragma: no cover - cache must never break business writes
        logger.warning("Could not clear report cache", exc_info=True)


async def build_project_audit(db: AsyncSession, project: Project) -> dict:
    """Build the complete financial audit of one project."""
    expenses = (
        await db.execute(
            select(ExpenseRecord)
            .options(selectinload(ExpenseRecord.warehouse_item))
            .where(ExpenseRecord.project_id == project.id)
            .order_by(ExpenseRecord.date, ExpenseRecord.id)
        )
    ).scalars().all()

    invoices = (
        await db.execute(
            select(Invoice)
            .options(selectinload(Invoice.items))
            .where(Invoice.project_id == project.id)
            .order_by(Invoice.date, Invoice.id)
        )
    ).scalars().all()

    # ----------------------------- expenses -----------------------------
    seasonal_usd = seasonal_syp = daily_usd = daily_syp = 0.0
    by_category: dict[str, dict] = {}
    pesticide_usage: list[dict] = []

    for expense in expenses:
        if expense.expense_nature == "SEASONAL":
            seasonal_usd += expense.total_amount_usd
            seasonal_syp += expense.total_amount_syp
        else:
            daily_usd += expense.total_amount_usd
            daily_syp += expense.total_amount_syp

        bucket = by_category.setdefault(
            expense.category,
            {"total_usd": 0.0, "total_syp": 0.0},
        )
        bucket["total_usd"] += expense.total_amount_usd
        bucket["total_syp"] += expense.total_amount_syp

        if expense.category == "PESTICIDE":
            pesticide_usage.append(
                {
                    "date": expense.date,
                    "item_name": expense.item_name,
                    "pharmacy_name": expense.pharmacy_name,
                    "quantity_used": expense.quantity_used,
                    "unit": expense.warehouse_item.unit if expense.warehouse_item else "",
                    "total_usd": expense.total_amount_usd,
                    "total_syp": expense.total_amount_syp,
                }
            )

    expenses_usd = money(seasonal_usd + daily_usd)
    expenses_syp = money(seasonal_syp + daily_syp)

    categories = [
        CategoryBreakdown(
            category=key,
            label=CATEGORY_LABELS.get(key, key),
            total_usd=money(value["total_usd"]),
            total_syp=money(value["total_syp"]),
            share_pct=round(value["total_usd"] / expenses_usd * 100, 2)
            if expenses_usd > 0
            else 0.0,
        )
        for key, value in by_category.items()
    ]
    categories.sort(key=lambda entry: entry.total_usd, reverse=True)

    expense_block = ExpenseBreakdown(
        seasonal_usd=money(seasonal_usd),
        seasonal_syp=money(seasonal_syp),
        daily_usd=money(daily_usd),
        daily_syp=money(daily_syp),
        total_usd=expenses_usd,
        total_syp=expenses_syp,
        by_category=categories,
        pesticide_usage=[PesticideUsage(**row) for row in pesticide_usage],
    )

    # ------------------------------ sales -------------------------------
    gross_weight = net_weight = 0.0
    box_count = 0
    commission_usd = commission_syp = 0.0
    polystyrene_usd = polystyrene_syp = 0.0
    fuel_usd = fuel_syp = 0.0
    other_usd = other_syp = 0.0
    gross_usd = gross_syp = 0.0
    net_sales_usd = net_sales_syp = 0.0
    crops: dict[str, dict] = {}

    for invoice in invoices:
        rate = float(invoice.exchange_rate or 0)
        gross_usd_i, gross_syp_i = convert_invoice_amount(
            invoice.total_gross, invoice.currency, rate
        )
        commission_usd_i, commission_syp_i = convert_invoice_amount(
            invoice.commission_amount, invoice.currency, rate
        )
        poly_usd_i, poly_syp_i = convert_invoice_amount(
            invoice.polystyrene_expense, invoice.currency, rate
        )
        fuel_usd_i, fuel_syp_i = convert_invoice_amount(
            invoice.vehicle_fuel_expense, invoice.currency, rate
        )
        other_usd_i, other_syp_i = convert_invoice_amount(
            invoice.other_deductions, invoice.currency, rate
        )

        gross_usd += gross_usd_i
        gross_syp += gross_syp_i
        commission_usd += commission_usd_i
        commission_syp += commission_syp_i
        polystyrene_usd += poly_usd_i
        polystyrene_syp += poly_syp_i
        fuel_usd += fuel_usd_i
        fuel_syp += fuel_syp_i
        other_usd += other_usd_i
        other_syp += other_syp_i
        net_sales_usd += invoice.net_total_usd
        net_sales_syp += invoice.net_total_syp

        for item in invoice.items:
            net_weight += item.net_weight
            gross_weight += item.gross_weight
            box_count += item.box_count
            revenue_usd, revenue_syp = convert_invoice_amount(
                item.subtotal, invoice.currency, rate
            )
            crop = crops.setdefault(
                item.crop_name,
                {
                    "net_weight": 0.0,
                    "gross_weight": 0.0,
                    "box_count": 0,
                    "revenue_usd": 0.0,
                    "revenue_syp": 0.0,
                },
            )
            crop["net_weight"] += item.net_weight
            crop["gross_weight"] += item.gross_weight
            crop["box_count"] += item.box_count
            crop["revenue_usd"] += revenue_usd
            crop["revenue_syp"] += revenue_syp

    crop_rows = [
        CropBreakdown(
            crop_name=name,
            net_weight=money(values["net_weight"]),
            gross_weight=money(values["gross_weight"]),
            box_count=values["box_count"],
            revenue_usd=money(values["revenue_usd"]),
            revenue_syp=money(values["revenue_syp"]),
            share_pct=round(values["revenue_usd"] / gross_usd * 100, 2)
            if gross_usd > 0
            else 0.0,
        )
        for name, values in crops.items()
    ]
    crop_rows.sort(key=lambda entry: entry.revenue_usd, reverse=True)

    sales_block = SalesBreakdown(
        invoice_count=len(invoices),
        gross_weight=money(gross_weight),
        net_weight=money(net_weight),
        box_count=box_count,
        total_gross_usd=money(gross_usd),
        total_gross_syp=money(gross_syp),
        commission_usd=money(commission_usd),
        commission_syp=money(commission_syp),
        polystyrene_usd=money(polystyrene_usd),
        polystyrene_syp=money(polystyrene_syp),
        vehicle_fuel_usd=money(fuel_usd),
        vehicle_fuel_syp=money(fuel_syp),
        other_deductions_usd=money(other_usd),
        other_deductions_syp=money(other_syp),
        net_sales_usd=money(net_sales_usd),
        net_sales_syp=money(net_sales_syp),
        by_crop=crop_rows,
    )

    # --------------------------- sharecropper ---------------------------
    gross_share_usd = gross_share_syp = 0.0
    invoice_deduction_usd = invoice_deduction_syp = 0.0
    for invoice in invoices:
        gross_share_syp += invoice.sharecropper_gross_share_syp
        gross_share_usd += invoice_syp_to_usd(
            invoice, invoice.sharecropper_gross_share_syp
        )
        invoice_deduction_syp += invoice.sharecropper_expense_deduction_syp
        invoice_deduction_usd += invoice_syp_to_usd(
            invoice, invoice.sharecropper_expense_deduction_syp
        )

    separate_deduction_usd = sum(
        expense.sharecropper_deduction_usd
        for expense in expenses
        if expense.enters_sharecropper_calc
    )
    separate_deduction_syp = sum(
        expense.sharecropper_deduction_syp
        for expense in expenses
        if expense.enters_sharecropper_calc
    )

    total_deduction_usd = money(invoice_deduction_usd + separate_deduction_usd)
    total_deduction_syp = money(invoice_deduction_syp + separate_deduction_syp)
    payout_usd = money(gross_share_usd - total_deduction_usd)
    payout_syp = money(gross_share_syp - total_deduction_syp)

    sharecropper_block = SharecropperStatement(
        enabled=project.has_sharecropper,
        name=project.sharecropper_name,
        profit_pct=float(project.sharecropper_profit_pct),
        expense_pct=float(project.sharecropper_expense_pct),
        gross_share_usd=money(gross_share_usd),
        gross_share_syp=money(gross_share_syp),
        invoice_expense_deduction_usd=money(invoice_deduction_usd),
        invoice_expense_deduction_syp=money(invoice_deduction_syp),
        separate_expense_deduction_usd=money(separate_deduction_usd),
        separate_expense_deduction_syp=money(separate_deduction_syp),
        total_deductions_usd=total_deduction_usd,
        total_deductions_syp=total_deduction_syp,
        net_payout_usd=payout_usd,
        net_payout_syp=payout_syp,
    )

    # ----------------------------- net profit ---------------------------
    owner_profit_usd = money(net_sales_usd - expenses_usd - payout_usd)
    owner_profit_syp = money(net_sales_syp - expenses_syp - payout_syp)
    margin_pct = (
        round(owner_profit_usd / net_sales_usd * 100, 2) if net_sales_usd > 0 else 0.0
    )

    net_profit_block = NetProfitSummary(
        expenses_usd=expenses_usd,
        expenses_syp=expenses_syp,
        sales_net_usd=money(net_sales_usd),
        sales_net_syp=money(net_sales_syp),
        sharecropper_payout_usd=payout_usd,
        sharecropper_payout_syp=payout_syp,
        owner_net_profit_usd=owner_profit_usd,
        owner_net_profit_syp=owner_profit_syp,
        margin_pct=margin_pct,
    )

    greenhouses = max(int(project.greenhouse_count or 1), 1)
    greenhouse_block = GreenhouseMetrics(
        greenhouse_count=greenhouses,
        cost_usd=money(expenses_usd / greenhouses),
        cost_syp=money(expenses_syp / greenhouses),
        revenue_usd=money(net_sales_usd / greenhouses),
        revenue_syp=money(net_sales_syp / greenhouses),
        net_profit_usd=money(owner_profit_usd / greenhouses),
        net_profit_syp=money(owner_profit_syp / greenhouses),
    )

    project_info = ProjectInfo(
        id=project.id,
        name=project.name,
        greenhouse_count=project.greenhouse_count,
        crops_planted=project.crops_planted,
        season_start_date=project.season_start_date,
        season_end_date=project.season_end_date,
        is_active=project.is_active,
        has_sharecropper=project.has_sharecropper,
        sharecropper_name=project.sharecropper_name,
        sharecropper_profit_pct=float(project.sharecropper_profit_pct),
        sharecropper_expense_pct=float(project.sharecropper_expense_pct),
    )

    return {
        "project": project_info.model_dump(),
        "expenses": expense_block.model_dump(),
        "sales": sales_block.model_dump(),
        "sharecropper": sharecropper_block.model_dump(),
        "per_greenhouse_metrics": greenhouse_block.model_dump(),
        "net_profit": net_profit_block.model_dump(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_expense_count": len(expenses),
    }


def audit_to_financials(audit: dict) -> ProjectFinancialSummary:
    net = audit["net_profit"]
    greenhouse = audit["per_greenhouse_metrics"]
    share = audit["sharecropper"]
    return ProjectFinancialSummary(
        invoice_count=audit["sales"]["invoice_count"],
        expense_count=audit.get("_expense_count", 0),
        total_expenses_usd=net["expenses_usd"],
        total_expenses_syp=net["expenses_syp"],
        total_gross_sales_usd=audit["sales"]["total_gross_usd"],
        total_gross_sales_syp=audit["sales"]["total_gross_syp"],
        total_sales_usd=net["sales_net_usd"],
        total_sales_syp=net["sales_net_syp"],
        sharecropper_due_usd=share["net_payout_usd"],
        sharecropper_due_syp=share["net_payout_syp"],
        net_profit_usd=net["owner_net_profit_usd"],
        net_profit_syp=net["owner_net_profit_syp"],
        cost_per_greenhouse_usd=greenhouse["cost_usd"],
        revenue_per_greenhouse_usd=greenhouse["revenue_usd"],
        profit_per_greenhouse_usd=greenhouse["net_profit_usd"],
        cost_per_greenhouse_syp=greenhouse["cost_syp"],
        revenue_per_greenhouse_syp=greenhouse["revenue_syp"],
        profit_per_greenhouse_syp=greenhouse["net_profit_syp"],
    )


async def project_with_summary(db: AsyncSession, project: Project) -> ProjectWithSummary:
    audit = await build_project_audit(db, project)
    base = ProjectRead.model_validate(project).model_dump()
    return ProjectWithSummary(**base, financials=audit_to_financials(audit))


@router.get(
    "/reports/project/{project_id}/full-audit",
    response_model=FullAuditReport,
    summary="التقرير المالي الشامل لمشروع (مخزن مؤقتاً)",
)
@limiter.limit(settings.report_rate_limit)
@cached_report(settings.cache_ttl_seconds)
async def project_full_audit(
    request: Request,
    response: Response,
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(db, project_id, current_user)
    return await build_project_audit(db, project)


@router.get(
    "/reports/global-summary",
    response_model=GlobalSummary,
    summary="لوحة القيادة العامة لكل المشاريع",
)
@limiter.limit(settings.report_rate_limit)
@cached_report(settings.cache_ttl_seconds)
async def global_summary(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GlobalSummary:
    query = select(Project).order_by(Project.id)
    if not is_admin(current_user):
        query = query.where(Project.owner_id == current_user.id)
    projects = (await db.execute(query)).scalars().all()

    comparisons: list[ProjectComparison] = []
    totals = {
        "expenses_usd": 0.0,
        "expenses_syp": 0.0,
        "sales_usd": 0.0,
        "sales_syp": 0.0,
        "dues_usd": 0.0,
        "dues_syp": 0.0,
        "profit_usd": 0.0,
        "profit_syp": 0.0,
    }

    for project in projects:
        audit = await build_project_audit(db, project)
        net = audit["net_profit"]
        share = audit["sharecropper"]
        comparison = ProjectComparison(
            id=project.id,
            name=project.name,
            greenhouse_count=project.greenhouse_count,
            is_active=project.is_active,
            expenses_usd=net["expenses_usd"],
            expenses_syp=net["expenses_syp"],
            sales_usd=net["sales_net_usd"],
            sales_syp=net["sales_net_syp"],
            net_profit_usd=net["owner_net_profit_usd"],
            net_profit_syp=net["owner_net_profit_syp"],
            profit_per_greenhouse_usd=audit["per_greenhouse_metrics"]["net_profit_usd"],
        )
        comparisons.append(comparison)
        totals["expenses_usd"] += net["expenses_usd"]
        totals["expenses_syp"] += net["expenses_syp"]
        totals["sales_usd"] += net["sales_net_usd"]
        totals["sales_syp"] += net["sales_net_syp"]
        totals["dues_usd"] += share["net_payout_usd"]
        totals["dues_syp"] += share["net_payout_syp"]
        totals["profit_usd"] += net["owner_net_profit_usd"]
        totals["profit_syp"] += net["owner_net_profit_syp"]

    most_profitable = (
        max(comparisons, key=lambda entry: entry.net_profit_usd) if comparisons else None
    )
    most_costly = max(comparisons, key=lambda entry: entry.expenses_usd) if comparisons else None

    return GlobalSummary(
        projects_count=len(projects),
        active_projects=sum(1 for project in projects if project.is_active),
        total_greenhouses=sum(project.greenhouse_count for project in projects),
        totals=GlobalTotals(
            expenses_usd=money(totals["expenses_usd"]),
            expenses_syp=money(totals["expenses_syp"]),
            sales_usd=money(totals["sales_usd"]),
            sales_syp=money(totals["sales_syp"]),
            sharecropper_dues_usd=money(totals["dues_usd"]),
            sharecropper_dues_syp=money(totals["dues_syp"]),
            net_profit_usd=money(totals["profit_usd"]),
            net_profit_syp=money(totals["profit_syp"]),
        ),
        projects=comparisons,
        most_profitable=most_profitable,
        most_costly=most_costly,
    )


@router.get(
    "/crops/{crop_name}/history",
    response_model=CropHistoryResponse,
    summary="تاريخ مبيعات محصول معين",
)
async def crop_history(
    crop_name: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CropHistoryResponse:
    query = (
        select(InvoiceItem, Invoice, Project.name)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .join(Project, Invoice.project_id == Project.id)
        .where(InvoiceItem.crop_name.ilike(f"%{crop_name.strip()}%"))
        .order_by(Invoice.date, Invoice.id)
    )
    if not is_admin(current_user):
        query = query.where(Invoice.owner_id == current_user.id)
    if start_date:
        query = query.where(Invoice.date >= start_date)
    if end_date:
        query = query.where(Invoice.date <= end_date)

    rows = (await db.execute(query)).all()
    points: list[CropHistoryPoint] = []
    total_weight = 0.0
    total_usd = 0.0
    total_syp = 0.0

    for item, invoice, project_name in rows:
        revenue_usd, revenue_syp = convert_invoice_amount(
            item.subtotal, invoice.currency, float(invoice.exchange_rate or 0)
        )
        points.append(
            CropHistoryPoint(
                date=invoice.date,
                invoice_id=invoice.id,
                project_id=invoice.project_id,
                project_name=project_name,
                net_weight=item.net_weight,
                unit_price=item.unit_price,
                revenue_usd=revenue_usd,
                revenue_syp=revenue_syp,
            )
        )
        total_weight += item.net_weight
        total_usd += revenue_usd
        total_syp += revenue_syp

    return CropHistoryResponse(
        crop_name=crop_name,
        points=points,
        total_net_weight=money(total_weight),
        total_revenue_usd=money(total_usd),
        total_revenue_syp=money(total_syp),
    )


@router.post(
    "/reports/heavy-export",
    response_model=TaskAccepted,
    summary="توليد جرد شامل في الخلفية عبر Celery",
)
@limiter.limit(settings.report_rate_limit)
async def heavy_export(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> TaskAccepted:
    from worker import generate_full_inventory

    try:
        task = generate_full_inventory.delay(current_user.id)
    except Exception as exc:  # pragma: no cover - depends on broker availability
        logger.exception("Celery broker unavailable")
        raise BackgroundTaskError(
            "خدمة المهام الخلفية غير متاحة حالياً. تأكد من تشغيل Redis وعامل Celery."
        ) from exc

    return TaskAccepted(
        task_id=str(task.id),
        status="PENDING",
        message="تم إرسال مهمة الجرد الشامل إلى الخلفية بنجاح.",
    )
