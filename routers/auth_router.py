"""Authentication routes."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    limiter,
)
from config import settings
from database import get_db
from exceptions import ConflictError
from models import ExpenseRecord, Invoice, InvoiceItem, Project, User, WarehouseItem
from schemas import MessageResponse, Token, UserCreate, UserRead

router = APIRouter(prefix="/api", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="إنشاء حساب مزارع/مستثمر جديد",
)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    existing = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("اسم المستخدم مستخدم مسبقاً، يرجى اختيار اسم آخر.")

    user = User(
        username=payload.username.strip(),
        phone_number=payload.phone_number,
        hashed_password=hash_password(payload.password),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token, summary="تسجيل الدخول وإرجاع JWT")
@limiter.limit(settings.login_rate_limit)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await authenticate_user(db, form_data.username, form_data.password)
    token = create_access_token(user.id, user.username)
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserRead, summary="بيانات المستخدم الحالي")
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.delete(
    "/reset",
    response_model=MessageResponse,
    summary="تصفير جميع بيانات المستخدم الحالي",
)
async def reset_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    owner_id = current_user.id

    invoice_ids = select(Invoice.id).where(Invoice.owner_id == owner_id)
    await db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id.in_(invoice_ids)))
    await db.execute(delete(ExpenseRecord).where(ExpenseRecord.owner_id == owner_id))
    await db.execute(delete(Invoice).where(Invoice.owner_id == owner_id))
    await db.execute(delete(WarehouseItem).where(WarehouseItem.owner_id == owner_id))
    await db.execute(delete(Project).where(Project.owner_id == owner_id))
    await db.commit()

    from routers.reports import invalidate_reports_cache

    await invalidate_reports_cache()

    counts = {
        "projects": (
            await db.execute(
                select(func.count(Project.id)).where(Project.owner_id == owner_id)
            )
        ).scalar_one(),
        "warehouse_items": (
            await db.execute(
                select(func.count(WarehouseItem.id)).where(WarehouseItem.owner_id == owner_id)
            )
        ).scalar_one(),
        "expenses": (
            await db.execute(
                select(func.count(ExpenseRecord.id)).where(ExpenseRecord.owner_id == owner_id)
            )
        ).scalar_one(),
        "invoices": (
            await db.execute(
                select(func.count(Invoice.id)).where(Invoice.owner_id == owner_id)
            )
        ).scalar_one(),
    }
    return MessageResponse(
        message="تم تصفير جميع بيانات الحساب بنجاح.", success=all(v == 0 for v in counts.values())
    )
