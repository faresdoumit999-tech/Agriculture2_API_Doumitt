# main.py
import sentry_sdk
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, extract, delete
from typing import List, Optional
from datetime import date
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.responses import JSONResponse
from sqlalchemy.orm import selectinload
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import models, schemas
from config import settings
from database import get_db
from exceptions import DoumittBaseException, UserAlreadyExistsError
from auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_current_admin
)
from routers import invoices

# ==========================================
# 🛡️ تهيئة Sentry لاصطياد الأخطاء
# ==========================================
sentry_sdk.init(
    dsn="",
    traces_sample_rate=1.0,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = aioredis.from_url(settings.redis_url, encoding="utf8", decode_responses=True)
    FastAPICache.init(RedisBackend(redis), prefix="doumitt-cache")
    yield

app = FastAPI(title="DOUMITT SaaS", lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.doumitt-app.com",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(DoumittBaseException)
async def doumitt_exception_handler(request: Request, exc: DoumittBaseException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_type": exc.__class__.__name__,
            "message": exc.message,
            "path": request.url.path
        }
    )

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 🔌 ربط راوتر الفواتير بالبدالة الرئيسية
app.include_router(invoices.router)

# ==========================================
# 🚪 مسارات تسجيل الدخول والاشتراك
# ==========================================
@app.post("/api/register", status_code=status.HTTP_201_CREATED)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    query = select(models.User).where(models.User.username == user.username)
    result = await db.execute(query)
    existing_user = result.scalars().first()

    if existing_user:
        raise UserAlreadyExistsError(username=user.username)

    hashed_password = get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_password)

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"message": "User created successfully"}

@app.post("/api/login", response_model=schemas.Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    query = select(models.User).where(models.User.username == form_data.username)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# ==========================================
# 📊 مسارات الإدارة والواجهة والتقارير
# ==========================================
@app.get("/api/admin/all_invoices", response_model=List[schemas.InvoiceResponse])
async def get_all_system_invoices(
        admin_user: models.User = Depends(get_current_admin),
        db: AsyncSession = Depends(get_db)
):
    query = select(models.Invoice).options(selectinload(models.Invoice.items)).order_by(models.Invoice.date.desc())
    result = await db.execute(query)
    return result.scalars().all()

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/expenses", response_model=schemas.ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def add_expense(expense: schemas.ExpenseCreate, current_user: models.User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    try:
        db_expense = models.ExpenseRecord(**expense.model_dump(), owner_id=current_user.id)
        db.add(db_expense)
        await db.commit()
        await db.refresh(db_expense)

        await FastAPICache.clear()
        return db_expense
    except Exception as e:
        await db.rollback()
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="فشل حفظ المصروف")

@app.get("/api/summary", response_model=schemas.SummaryResponse)
@cache(expire=60)
async def get_summary(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    income_query = select(func.sum(models.Invoice.net_total)).where(models.Invoice.owner_id == current_user.id)
    income_result = await db.execute(income_query)
    total_income = income_result.scalar() or 0.0

    expenses_query = select(func.sum(models.ExpenseRecord.amount)).where(
        models.ExpenseRecord.owner_id == current_user.id)
    expenses_result = await db.execute(expenses_query)
    total_expenses = expenses_result.scalar() or 0.0

    net_profit = total_income - total_expenses
    return schemas.SummaryResponse(total_income=total_income, total_expenses=total_expenses, net_profit=net_profit)

@app.get("/api/reports/summary", response_model=schemas.ReportSummaryResponse)
async def get_reports_summary(start_date: Optional[date] = None, end_date: Optional[date] = None,
                              crop_name: Optional[str] = None, current_user: models.User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    query = select(
        func.sum(models.Invoice.total_gross).label("total_gross"),
        func.sum(models.Invoice.deductions).label("total_deductions"),
        func.sum(models.Invoice.net_total).label("total_net"),
        func.sum(models.InvoiceItem.net_weight).label("total_weight")
    ).join(models.InvoiceItem).where(models.Invoice.owner_id == current_user.id)

    if start_date: query = query.where(models.Invoice.date >= start_date)
    if end_date: query = query.where(models.Invoice.date <= end_date)
    if crop_name and crop_name != "الكل": query = query.where(models.InvoiceItem.crop_name == crop_name)

    result = await db.execute(query)
    row = result.first()

    return schemas.ReportSummaryResponse(
        total_gross=row.total_gross or 0.0 if row else 0.0,
        total_deductions=row.total_deductions or 0.0 if row else 0.0,
        total_net=row.total_net or 0.0 if row else 0.0,
        total_weight=row.total_weight or 0.0 if row else 0.0
    )

@app.get("/api/crops", response_model=list[str])
@cache(expire=60 * 30)
async def get_crops(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(models.InvoiceItem.crop_name).join(models.Invoice).where(
        models.Invoice.owner_id == current_user.id).distinct()
    result = await db.execute(query)
    return list(result.scalars().all())

@app.get("/api/crops/{crop_name}/history", response_model=schemas.CropHistoryResponse)
async def get_crop_history(crop_name: str, year: Optional[int] = None, skip: int = 0, limit: int = 50,
                           current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(models.InvoiceItem, models.Invoice.date).join(models.Invoice).where(
        models.InvoiceItem.crop_name == crop_name, models.Invoice.owner_id == current_user.id)

    if year: query = query.where(extract('year', models.Invoice.date) == year)

    query = query.order_by(models.Invoice.date.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    items = result.all()

    history_list, total_w, total_r = [], 0.0, 0.0
    for item, inv_date in items:
        history_list.append(
            schemas.CropHistoryItem(invoice_date=inv_date, box_count=item.box_count, net_weight=item.net_weight,
                                    unit_price=item.unit_price, subtotal=item.subtotal))
        total_w += item.net_weight
        total_r += item.subtotal

    return schemas.CropHistoryResponse(crop_name=crop_name, history=history_list, total_weight=total_w,
                                       total_revenue=total_r)

@app.delete("/api/reset")
async def reset_database(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        query = select(models.Invoice).where(models.Invoice.owner_id == current_user.id)
        result = await db.execute(query)
        invoices = result.scalars().all()

        for inv in invoices:
            await db.delete(inv)

        stmt = delete(models.ExpenseRecord).where(models.ExpenseRecord.owner_id == current_user.id)
        await db.execute(stmt)

        await db.commit()

        await FastAPICache.clear()
        return {"message": "User specific data wiped"}
    except Exception as e:
        await db.rollback()
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="فشل تصفير الحساب")