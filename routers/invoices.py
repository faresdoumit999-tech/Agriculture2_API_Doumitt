"""Vegetable-market invoices."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user, get_owned_project, is_admin
from database import get_db
from exceptions import CurrencyError, NotFoundError
from models import Invoice, InvoiceItem, User
from routers.reports import invalidate_reports_cache
from schemas import (
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceRead,
    InvoiceUpdate,
    MessageResponse,
)
from services.sharecropper_service import calculate_invoice

router = APIRouter(prefix="/api/invoices", tags=["Market Invoices"])

CALC_COLUMNS = (
    "total_gross",
    "commission_amount",
    "polystyrene_expense",
    "vehicle_fuel_expense",
    "other_deductions",
    "net_total",
    "net_total_usd",
    "net_total_syp",
    "sharecropper_applied_profit_pct",
    "sharecropper_applied_expense_pct",
    "sharecropper_gross_share_syp",
    "sharecropper_expense_deduction_syp",
    "sharecropper_net_payout_syp",
    "sharecropper_net_payout_usd",
    "owner_net_profit_syp",
    "owner_net_profit_usd",
)


async def _get_invoice(db: AsyncSession, invoice_id: int, user: User) -> Invoice:
    query = (
        select(Invoice)
        .options(selectinload(Invoice.items), selectinload(Invoice.project))
        .where(Invoice.id == invoice_id)
    )
    if not is_admin(user):
        query = query.where(Invoice.owner_id == user.id)
    invoice = (await db.execute(query)).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("الفاتورة غير موجودة أو لا تملك صلاحية الوصول إليها.")
    return invoice


def _apply_calculation(invoice: Invoice, calc: dict) -> None:
    for column in CALC_COLUMNS:
        setattr(invoice, column, calc[column])


@router.post(
    "",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="إضافة فاتورة سوق خضرة متعددة الأصناف",
)
async def create_invoice(
    payload: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRead:
    project = await get_owned_project(db, payload.project_id, current_user)
    rate = float(payload.exchange_rate or 0)

    calc = calculate_invoice(
        payload.items,
        commission_amount=payload.commission_amount,
        polystyrene_expense=payload.polystyrene_expense,
        vehicle_fuel_expense=payload.vehicle_fuel_expense,
        other_deductions=payload.other_deductions,
        currency=payload.currency,
        exchange_rate=rate,
        project=project,
    )

    invoice = Invoice(
        owner_id=project.owner_id,
        project_id=project.id,
        date=payload.date,
        currency=payload.currency,
        exchange_rate=rate,
    )
    _apply_calculation(invoice, calc)
    invoice.items = [InvoiceItem(**row) for row in calc["items"]]

    db.add(invoice)
    await db.commit()
    await invalidate_reports_cache()
    return InvoiceRead.model_validate(invoice)


@router.get(
    "",
    response_model=list[InvoiceRead],
    summary="جلب الفواتير مع فلاتر شاملة",
)
async def list_invoices(
    project_id: int | None = Query(default=None),
    crop_name: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Invoice]:
    query = (
        select(Invoice)
        .options(selectinload(Invoice.items))
        .order_by(Invoice.date.desc(), Invoice.id.desc())
    )
    if not is_admin(current_user):
        query = query.where(Invoice.owner_id == current_user.id)
    if project_id is not None:
        query = query.where(Invoice.project_id == project_id)
    if crop_name:
        query = query.where(
            Invoice.items.any(InvoiceItem.crop_name.ilike(f"%{crop_name.strip()}%"))
        )
    if start_date:
        query = query.where(Invoice.date >= start_date)
    if end_date:
        query = query.where(Invoice.date <= end_date)
    query = query.offset(skip).limit(limit)

    return list((await db.execute(query)).scalars().all())


@router.put(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="تعديل فاتورة وإعادة حساب حصة الشغّيل وصافي المالك",
)
async def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRead:
    invoice = await _get_invoice(db, invoice_id, current_user)
    data = payload.model_dump(exclude_unset=True)

    if "project_id" in data and data["project_id"] != invoice.project_id:
        project = await get_owned_project(db, data["project_id"], current_user)
        invoice.project = project
        invoice.project_id = project.id
        invoice.owner_id = project.owner_id
    project = invoice.project

    for field in ("date", "currency"):
        if field in data and data[field] is not None:
            setattr(invoice, field, data[field])
    for field in (
        "commission_amount",
        "polystyrene_expense",
        "vehicle_fuel_expense",
        "other_deductions",
    ):
        if field in data and data[field] is not None:
            setattr(invoice, field, float(data[field]))
    if "exchange_rate" in data and data["exchange_rate"] is not None:
        invoice.exchange_rate = float(data["exchange_rate"])

    if invoice.currency == "USD" and float(invoice.exchange_rate or 0) <= 0:
        raise CurrencyError("سعر الصرف مطلوب ويجب أن يكون أكبر من صفر عند الفاتورة بالدولار.")

    if payload.items is not None:
        items_payload = payload.items
    else:
        items_payload = [
            InvoiceItemCreate(
                crop_name=item.crop_name,
                box_count=item.box_count,
                gross_weight=item.gross_weight,
                net_weight=item.net_weight,
                unit_price=item.unit_price,
            )
            for item in invoice.items
        ]

    calc = calculate_invoice(
        items_payload,
        commission_amount=invoice.commission_amount,
        polystyrene_expense=invoice.polystyrene_expense,
        vehicle_fuel_expense=invoice.vehicle_fuel_expense,
        other_deductions=invoice.other_deductions,
        currency=invoice.currency,
        exchange_rate=float(invoice.exchange_rate or 0),
        project=project,
    )
    _apply_calculation(invoice, calc)

    if payload.items is not None:
        invoice.items.clear()
        invoice.items.extend(InvoiceItem(**row) for row in calc["items"])

    await db.commit()
    await invalidate_reports_cache()
    return InvoiceRead.model_validate(invoice)


@router.delete(
    "/{invoice_id}",
    response_model=MessageResponse,
    summary="حذف فاتورة وجميع أصنافها",
)
async def delete_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    invoice = await _get_invoice(db, invoice_id, current_user)
    await db.delete(invoice)
    await db.commit()
    await invalidate_reports_cache()
    return MessageResponse(message="تم حذف الفاتورة وجميع أصنافها بنجاح.")
