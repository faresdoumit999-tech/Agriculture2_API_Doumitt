"""Seasonal and daily expenses."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user, get_owned_project, is_admin
from database import get_db
from exceptions import CurrencyError, NotFoundError
from models import ExpenseRecord, User
from routers.reports import invalidate_reports_cache
from schemas import (
    ExpenseCreate,
    ExpenseRead,
    ExpenseUpdate,
    MessageResponse,
)
from services.currency_service import dual_amount, money
from services.sharecropper_service import apply_expense_sharecropper
from services.warehouse_service import restore_warehouse_quantity

router = APIRouter(prefix="/api/expenses", tags=["Expenses"])


async def _get_expense(db: AsyncSession, expense_id: int, user: User) -> ExpenseRecord:
    query = (
        select(ExpenseRecord)
        .options(selectinload(ExpenseRecord.project))
        .where(ExpenseRecord.id == expense_id)
    )
    if not is_admin(user):
        query = query.where(ExpenseRecord.owner_id == user.id)
    expense = (await db.execute(query)).scalar_one_or_none()
    if expense is None:
        raise NotFoundError("المصروف غير موجود أو لا تملك صلاحية الوصول إليه.")
    return expense


@router.post(
    "",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="تسجيل مصروف موسمي أو يومي مباشر",
)
async def create_expense(
    payload: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRead:
    project = await get_owned_project(db, payload.project_id, current_user)
    amounts = dual_amount(
        payload.quantity_used * payload.unit_price,
        payload.currency,
        payload.exchange_rate,
    )

    expense = ExpenseRecord(
        owner_id=project.owner_id,
        project_id=project.id,
        date=payload.date,
        expense_nature=payload.expense_nature,
        category=payload.category,
        item_name=payload.item_name.strip(),
        pharmacy_name=payload.pharmacy_name.strip() if payload.pharmacy_name else None,
        quantity_used=payload.quantity_used,
        unit_price=money(payload.unit_price),
        currency=payload.currency,
        exchange_rate=amounts.exchange_rate,
        total_amount_usd=amounts.usd,
        total_amount_syp=amounts.syp,
    )
    expense.project = project

    apply_expense_sharecropper(
        expense,
        project,
        enters=payload.enters_sharecropper_calc,
        custom_pct=payload.custom_sharecropper_pct,
    )

    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    await invalidate_reports_cache()
    return ExpenseRead.model_validate(expense)


@router.get(
    "",
    response_model=list[ExpenseRead],
    summary="جدول المصاريف مع فلاتر شاملة",
)
async def list_expenses(
    project_id: int | None = Query(default=None),
    expense_nature: str | None = Query(default=None),
    category: str | None = Query(default=None),
    pharmacy_name: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=300, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseRecord]:
    query = select(ExpenseRecord).order_by(ExpenseRecord.date.desc(), ExpenseRecord.id.desc())
    if not is_admin(current_user):
        query = query.where(ExpenseRecord.owner_id == current_user.id)
    if project_id is not None:
        query = query.where(ExpenseRecord.project_id == project_id)
    if expense_nature:
        query = query.where(ExpenseRecord.expense_nature == expense_nature)
    if category:
        query = query.where(ExpenseRecord.category == category)
    if pharmacy_name:
        query = query.where(ExpenseRecord.pharmacy_name.ilike(f"%{pharmacy_name.strip()}%"))
    if start_date:
        query = query.where(ExpenseRecord.date >= start_date)
    if end_date:
        query = query.where(ExpenseRecord.date <= end_date)
    query = query.offset(skip).limit(limit)

    return list((await db.execute(query)).scalars().all())


@router.put(
    "/{expense_id}",
    response_model=ExpenseRead,
    summary="تعديل مصروف مع إعادة حساب كل المعادلات فوراً",
)
async def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRead:
    expense = await _get_expense(db, expense_id, current_user)
    data = payload.model_dump(exclude_unset=True)

    if "project_id" in data and data["project_id"] != expense.project_id:
        project = await get_owned_project(db, data["project_id"], current_user)
        expense.project = project
        expense.project_id = project.id
        expense.owner_id = project.owner_id
    project = expense.project

    for field in ("date", "expense_nature", "category", "item_name", "quantity_used", "unit_price"):
        if field in data and data[field] is not None:
            setattr(expense, field, data[field])

    if "pharmacy_name" in data:
        expense.pharmacy_name = (
            data["pharmacy_name"].strip() if data["pharmacy_name"] else None
        )

    if "currency" in data and data["currency"] is not None:
        expense.currency = data["currency"]
    if "exchange_rate" in data and data["exchange_rate"] is not None:
        expense.exchange_rate = float(data["exchange_rate"])

    if expense.currency == "USD" and float(expense.exchange_rate or 0) <= 0:
        raise CurrencyError("سعر الصرف مطلوب ويجب أن يكون أكبر من صفر عند الإدخال بالدولار.")

    amounts = dual_amount(
        expense.quantity_used * expense.unit_price,
        expense.currency,
        expense.exchange_rate,
    )
    expense.exchange_rate = amounts.exchange_rate
    expense.total_amount_usd = amounts.usd
    expense.total_amount_syp = amounts.syp

    if "enters_sharecropper_calc" in data:
        enters = data["enters_sharecropper_calc"]
    elif "category" in data:
        enters = None
    else:
        enters = expense.enters_sharecropper_calc

    custom_pct = (
        data["custom_sharecropper_pct"]
        if "custom_sharecropper_pct" in data
        else expense.custom_sharecropper_pct
    )
    apply_expense_sharecropper(expense, project, enters=enters, custom_pct=custom_pct)

    await db.commit()
    await db.refresh(expense)
    await invalidate_reports_cache()
    return ExpenseRead.model_validate(expense)


@router.delete(
    "/{expense_id}",
    response_model=MessageResponse,
    summary="حذف مصروف وإعادة الكمية المسحوبة للمستودع إن وجدت",
)
async def delete_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    expense = await _get_expense(db, expense_id, current_user)
    restored = expense.warehouse_item_id is not None
    await restore_warehouse_quantity(db, expense)
    await db.delete(expense)
    await db.commit()
    await invalidate_reports_cache()

    message = "تم حذف المصروف بنجاح."
    if restored:
        message += " وأُعيدت الكمية المسحوبة إلى رصيد المستودع."
    return MessageResponse(message=message)
