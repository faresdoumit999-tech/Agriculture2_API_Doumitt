"""Central warehouse: purchases and decimal partial withdrawals."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_owned_project, is_admin
from exceptions import InsufficientStockError, NotFoundError
from models import ExpenseRecord, User, WarehouseItem
from schemas import ConsumeRequest, WarehouseItemCreate
from services.currency_service import compute_purchase, dual_amount, money, quantity
from services.sharecropper_service import apply_expense_sharecropper


async def create_warehouse_purchase(
    db: AsyncSession, user: User, data: WarehouseItemCreate
) -> WarehouseItem:
    totals = compute_purchase(data.quantity, data.unit_price, data.currency, data.exchange_rate)
    item = WarehouseItem(
        owner_id=user.id,
        product_name=data.product_name.strip(),
        pharmacy_name=data.pharmacy_name.strip(),
        purchase_date=data.purchase_date,
        initial_quantity=quantity(data.quantity),
        remaining_quantity=quantity(data.quantity),
        unit=data.unit.strip(),
        currency=totals["currency"],
        exchange_rate=totals["exchange_rate"],
        unit_price_usd=totals["unit_price_usd"],
        unit_price_syp=totals["unit_price_syp"],
        total_cost_usd=totals["total_cost_usd"],
        total_cost_syp=totals["total_cost_syp"],
    )
    db.add(item)
    await db.flush()
    return item


async def get_warehouse_item(db: AsyncSession, item_id: int, user: User) -> WarehouseItem:
    query = select(WarehouseItem).where(WarehouseItem.id == item_id)
    if not is_admin(user):
        query = query.where(WarehouseItem.owner_id == user.id)
    item = (await db.execute(query)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("غرض المستودع غير موجود أو لا تملك صلاحية الوصول إليه.")
    return item


async def consume_from_warehouse(
    db: AsyncSession, user: User, data: ConsumeRequest
) -> tuple[ExpenseRecord, WarehouseItem]:
    """Withdraw a decimal quantity and create the matching daily expense.

    The stock check happens before any mutation, then ``remaining_quantity`` is
    reduced and a fully priced ``ExpenseRecord`` is attached to the project.
    """
    project = await get_owned_project(db, data.project_id, user)
    item = await get_warehouse_item(db, data.warehouse_item_id, user)

    if project.owner_id != item.owner_id:
        raise InsufficientStockError(
            "لا يمكن صرف غرض من مستودع مستخدم آخر إلى مشروع لا يتبع لنفس الحساب."
        )

    used = quantity(data.quantity_used)
    if used <= 0:
        raise InsufficientStockError("الكمية المسحوبة يجب أن تكون أكبر من صفر.")

    available = quantity(item.remaining_quantity)
    if used > available + 1e-9:
        raise InsufficientStockError(
            f"الكمية المتوفرة في المستودع غير كافية. المتاح: {available} {item.unit}",
            details={
                "available": available,
                "requested": used,
                "unit": item.unit,
            },
        )

    unit_price = item.unit_price_usd if item.currency == "USD" else item.unit_price_syp
    amounts = dual_amount(used * unit_price, item.currency, item.exchange_rate)

    expense = ExpenseRecord(
        owner_id=item.owner_id,
        project_id=project.id,
        warehouse_item_id=item.id,
        date=data.date,
        expense_nature=data.expense_nature,
        category=data.category,
        item_name=item.product_name,
        pharmacy_name=item.pharmacy_name,
        quantity_used=used,
        unit_price=money(unit_price),
        currency=item.currency,
        exchange_rate=item.exchange_rate,
        total_amount_usd=amounts.usd,
        total_amount_syp=amounts.syp,
    )
    expense.project = project
    expense.warehouse_item = item

    apply_expense_sharecropper(
        expense,
        project,
        enters=data.enters_sharecropper_calc,
        custom_pct=data.custom_sharecropper_pct,
    )

    item.remaining_quantity = quantity(max(0.0, available - used))
    db.add(expense)
    await db.flush()
    return expense, item


async def restore_warehouse_quantity(db: AsyncSession, expense: ExpenseRecord) -> None:
    """Return a consumed quantity to the warehouse when its expense is deleted."""
    if not expense.warehouse_item_id:
        return
    item = await db.get(WarehouseItem, expense.warehouse_item_id)
    if item is None:
        return
    restored = quantity(item.remaining_quantity + expense.quantity_used)
    item.remaining_quantity = quantity(min(item.initial_quantity, restored))
    await db.flush()
