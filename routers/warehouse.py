"""Central warehouse and agricultural-pharmacy audit."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user, get_owned_project, is_admin
from database import get_db
from exceptions import ConflictError, CurrencyError, NotFoundError
from models import ExpenseRecord, User, WarehouseItem
from routers.reports import invalidate_reports_cache
from schemas import (
    ConsumeRequest,
    ConsumeResponse,
    ExpenseRead,
    WarehouseItemCreate,
    WarehouseItemRead,
    WarehouseItemUpdate,
)
from services.currency_service import compute_purchase, money, quantity
from services.warehouse_service import consume_from_warehouse, create_warehouse_purchase

router = APIRouter(prefix="/api/warehouse", tags=["Warehouse & Pharmacies"])


def stock_status(initial: float, remaining: float) -> str:
    if remaining <= 1e-9:
        return "out"
    if initial > 0 and remaining <= initial * 0.2:
        return "low"
    return "ok"


def warehouse_read(item: WarehouseItem) -> WarehouseItemRead:
    consumed = max(0.0, quantity(item.initial_quantity - item.remaining_quantity))
    return WarehouseItemRead.model_validate(item).model_copy(
        update={
            "consumed_quantity": consumed,
            "stock_status": stock_status(item.initial_quantity, item.remaining_quantity),
        }
    )


@router.post(
    "/items",
    response_model=WarehouseItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="شراء دواء أو سماد وإدخاله للمستودع",
)
async def create_item(
    payload: WarehouseItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarehouseItemRead:
    item = await create_warehouse_purchase(db, current_user, payload)
    await db.commit()
    await db.refresh(item)
    await invalidate_reports_cache()
    return warehouse_read(item)


@router.get(
    "/items",
    response_model=list[WarehouseItemRead],
    summary="جرد المستودع الحالي مع تنبيهات النفاد",
)
async def list_items(
    pharmacy_name: str | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WarehouseItemRead]:
    query = select(WarehouseItem).order_by(WarehouseItem.purchase_date.desc(), WarehouseItem.id.desc())
    if not is_admin(current_user):
        query = query.where(WarehouseItem.owner_id == current_user.id)
    if pharmacy_name:
        query = query.where(WarehouseItem.pharmacy_name.ilike(f"%{pharmacy_name.strip()}%"))

    items = (await db.execute(query)).scalars().all()
    rows = [warehouse_read(item) for item in items]
    if low_stock_only:
        rows = [row for row in rows if row.stock_status in {"low", "out"}]
    return rows[skip : skip + limit]


@router.put(
    "/items/{item_id}",
    response_model=WarehouseItemRead,
    summary="تعديل بيانات غرض في المستودع",
)
async def update_item(
    item_id: int,
    payload: WarehouseItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarehouseItemRead:
    query = select(WarehouseItem).where(WarehouseItem.id == item_id)
    if not is_admin(current_user):
        query = query.where(WarehouseItem.owner_id == current_user.id)
    item = (await db.execute(query)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("غرض المستودع غير موجود أو لا تملك صلاحية الوصول إليه.")

    data = payload.model_dump(exclude_unset=True)
    currency = data.get("currency", item.currency)
    unit_price = data.get(
        "unit_price",
        item.unit_price_usd if item.currency == "USD" else item.unit_price_syp,
    )
    exchange_rate = data.get("exchange_rate")
    if exchange_rate is None:
        exchange_rate = item.exchange_rate
    if currency == "USD" and float(exchange_rate or 0) <= 0:
        raise CurrencyError("سعر الصرف مطلوب عند تسعير الغرض بالدولار.")

    initial = float(data.get("initial_quantity", item.initial_quantity))
    remaining = float(data.get("remaining_quantity", item.remaining_quantity))
    if remaining > initial + 1e-9:
        raise ConflictError("الكمية المتبقية لا يمكن أن تتجاوز الكمية الابتدائية.")
    if remaining < 0:
        raise ConflictError("الكمية المتبقية لا يمكن أن تكون سالبة.")

    totals = compute_purchase(initial, float(unit_price), currency, exchange_rate)

    for field in ("product_name", "pharmacy_name", "purchase_date", "unit"):
        if field in data and data[field] is not None:
            setattr(item, field, data[field])

    item.initial_quantity = quantity(initial)
    item.remaining_quantity = quantity(remaining)
    item.currency = totals["currency"]
    item.exchange_rate = totals["exchange_rate"]
    item.unit_price_usd = totals["unit_price_usd"]
    item.unit_price_syp = totals["unit_price_syp"]
    item.total_cost_usd = totals["total_cost_usd"]
    item.total_cost_syp = totals["total_cost_syp"]

    await db.commit()
    await db.refresh(item)
    await invalidate_reports_cache()
    return warehouse_read(item)


@router.post(
    "/consume",
    response_model=ConsumeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="سحب كمية عشرية من المستودع وترحيلها كمصروف على مشروع",
)
async def consume_item(
    payload: ConsumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsumeResponse:
    expense, item = await consume_from_warehouse(db, current_user, payload)
    await db.commit()
    await db.refresh(expense)
    await db.refresh(item)
    await invalidate_reports_cache()
    return ConsumeResponse(
        expense=ExpenseRead.model_validate(expense),
        warehouse_item=warehouse_read(item),
    )


@router.get(
    "/pharmacies-audit",
    summary="تقرير جرد الصيدليات الزراعية الشامل",
)
async def pharmacies_audit(
    pharmacy_name: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    project_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if project_id is not None:
        await get_owned_project(db, project_id, current_user)

    query = select(WarehouseItem).order_by(WarehouseItem.purchase_date, WarehouseItem.id)
    if not is_admin(current_user):
        query = query.where(WarehouseItem.owner_id == current_user.id)
    if pharmacy_name:
        query = query.where(WarehouseItem.pharmacy_name.ilike(f"%{pharmacy_name.strip()}%"))
    if start_date:
        query = query.where(WarehouseItem.purchase_date >= start_date)
    if end_date:
        query = query.where(WarehouseItem.purchase_date <= end_date)

    items = (await db.execute(query)).scalars().all()
    item_ids = [item.id for item in items]

    consumptions: dict[int, list[ExpenseRecord]] = defaultdict(list)
    if item_ids:
        expense_query = (
            select(ExpenseRecord)
            .options(selectinload(ExpenseRecord.project))
            .where(ExpenseRecord.warehouse_item_id.in_(item_ids))
            .order_by(ExpenseRecord.date, ExpenseRecord.id)
        )
        if project_id is not None:
            expense_query = expense_query.where(ExpenseRecord.project_id == project_id)
        if start_date:
            expense_query = expense_query.where(ExpenseRecord.date >= start_date)
        if end_date:
            expense_query = expense_query.where(ExpenseRecord.date <= end_date)
        for expense in (await db.execute(expense_query)).scalars().all():
            consumptions[expense.warehouse_item_id].append(expense)

    pharmacies: dict[str, dict] = {}
    for item in items:
        used = consumptions.get(item.id, [])
        if project_id is not None and not used:
            continue

        bucket = pharmacies.setdefault(
            item.pharmacy_name,
            {
                "pharmacy_name": item.pharmacy_name,
                "items_count": 0,
                "total_purchased_usd": 0.0,
                "total_purchased_syp": 0.0,
                "total_consumed_usd": 0.0,
                "total_consumed_syp": 0.0,
                "items": [],
            },
        )
        bucket["items_count"] += 1
        bucket["total_purchased_usd"] += item.total_cost_usd
        bucket["total_purchased_syp"] += item.total_cost_syp
        bucket["total_consumed_usd"] += sum(expense.total_amount_usd for expense in used)
        bucket["total_consumed_syp"] += sum(expense.total_amount_syp for expense in used)
        bucket["items"].append(
            {
                "id": item.id,
                "product_name": item.product_name,
                "purchase_date": item.purchase_date,
                "initial_quantity": item.initial_quantity,
                "remaining_quantity": item.remaining_quantity,
                "consumed_quantity": quantity(
                    max(0.0, item.initial_quantity - item.remaining_quantity)
                ),
                "unit": item.unit,
                "currency": item.currency,
                "exchange_rate": item.exchange_rate,
                "unit_price_usd": item.unit_price_usd,
                "unit_price_syp": item.unit_price_syp,
                "total_cost_usd": item.total_cost_usd,
                "total_cost_syp": item.total_cost_syp,
                "consumptions": [
                    {
                        "expense_id": expense.id,
                        "date": expense.date,
                        "project_id": expense.project_id,
                        "project_name": expense.project.name if expense.project else None,
                        "quantity_used": expense.quantity_used,
                        "total_usd": expense.total_amount_usd,
                        "total_syp": expense.total_amount_syp,
                    }
                    for expense in used
                ],
            }
        )

    rows = list(pharmacies.values())
    for row in rows:
        row["total_purchased_usd"] = money(row["total_purchased_usd"])
        row["total_purchased_syp"] = money(row["total_purchased_syp"])
        row["total_consumed_usd"] = money(row["total_consumed_usd"])
        row["total_consumed_syp"] = money(row["total_consumed_syp"])
    rows.sort(key=lambda entry: entry["total_purchased_syp"], reverse=True)

    return {
        "pharmacies": rows,
        "totals": {
            "pharmacies_count": len(rows),
            "items_count": sum(row["items_count"] for row in rows),
            "purchased_usd": money(sum(row["total_purchased_usd"] for row in rows)),
            "purchased_syp": money(sum(row["total_purchased_syp"] for row in rows)),
            "consumed_usd": money(sum(row["total_consumed_usd"] for row in rows)),
            "consumed_syp": money(sum(row["total_consumed_syp"] for row in rows)),
        },
    }
