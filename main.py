from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import func, extract, delete
from typing import List, Optional
from datetime import datetime, timedelta, timezone, date
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.staticfiles import StaticFiles  # ضفنا هي الكلمة هون
import models, schemas
from database import SessionLocal, engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.responses import JSONResponse
from exceptions import DoumittBaseException, UserAlreadyExistsError, InvoiceNotFoundError
from sqlalchemy.orm import selectinload

app = FastAPI(title="DOUMITT SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.exception_handler(DoumittBaseException)
async def doumitt_exception_handler(request: Request, exc: DoumittBaseException):
    """
    هذا المعالج سيلتقط أي خطأ يورث من DoumittBaseException
    ويقوم بتغليفه في رد JSON احترافي موحد.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_type": exc.__class__.__name__,
            "message": exc.message,
            "path": request.url.path
        }
    )
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static") # 👈 ضيف هاد السطر


async def get_db():
    async with SessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()


# ==========================================
# 🔐 نظام الحماية والتشفير (AUTH SYSTEM)
# ==========================================
SECRET_KEY = "doumitt_super_secret_key_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # أسبوع كامل

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# 🌟 تحويل التحقق من المستخدم لـ Async
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="تعذر التحقق من الصلاحيات",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except JWTError:
        raise credentials_exception

    # البحث بالطريقة الصاروخية
    query = select(models.User).where(models.User.username == username)
    result = await db.execute(query)
    user = result.scalars().first()

    if user is None: raise credentials_exception
    return user


# ==========================================
# 🚪 مسارات تسجيل الدخول والاشتراك
# ==========================================
@app.post("/api/register")
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    query = select(models.User).where(models.User.username == user.username)
    result = await db.execute(query)
    existing_user = result.scalars().first()

    if existing_user:
        # هنا السيرفر يتحدث بلغة المشروع ويرمي الخطأ المخصص
        raise UserAlreadyExistsError(username=user.username)

    hashed_password = get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_password)

    db.add(new_user)  # add ما بتحتاج await لأنها بتتم بالذاكرة المحلية
    await db.commit()
    await db.refresh(new_user)

    return {"message": "User created successfully"}


@app.post("/api/login", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
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
# 📊 مسارات النظام (معزولة لكل مستخدم)
# ==========================================
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/invoices", response_model=schemas.InvoiceResponse)
async def add_invoice(invoice: schemas.InvoiceCreate, current_user: models.User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    db_invoice = models.Invoice(date=invoice.date, total_gross=invoice.total_gross, deductions=invoice.deductions,
                                net_total=invoice.net_total, owner_id=current_user.id)
    db.add(db_invoice)
    await db.commit()
    await db.refresh(db_invoice)

    for item in invoice.items:
        db_item = models.InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
        db.add(db_item)
    await db.commit()
    await db.refresh(db_invoice)
    return db_invoice


@app.post("/api/invoices/bulk", response_model=List[schemas.InvoiceResponse])
async def add_invoices_bulk(invoices: List[schemas.InvoiceCreate],
                            current_user: models.User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    db_invoices = []
    for invoice in invoices:
        db_invoice = models.Invoice(date=invoice.date, total_gross=invoice.total_gross, deductions=invoice.deductions,
                                    net_total=invoice.net_total, owner_id=current_user.id)
        db.add(db_invoice)
        await db.flush()  # Flush بيحتاج await بالنظام الجديد
        for item in invoice.items:
            db_item = models.InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
            db.add(db_item)
        db_invoices.append(db_invoice)
    await db.commit()
    for inv in db_invoices:
        await db.refresh(inv)
    return db_invoices


@app.get("/api/invoices", response_model=List[schemas.InvoiceResponse])
async def get_invoices(
        skip: int = 0,  # التجاوز (Offset) - الافتراضي 0
        limit: int = 20,  # الحد الأقصى (Limit) - الافتراضي 20
        current_user: models.User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    مسار جلب فواتير المزارع مع ميزة تقسيم الصفحات (Pagination)
    وجلب العناصر المرتبطة (Items) بشكل آمن ومتزامن.
    """
    query = (
        select(models.Invoice)
        .where(models.Invoice.owner_id == current_user.id)
        .options(selectinload(models.Invoice.items))  # 🌟 السر المعماري لتجنب أخطاء الـ Async
        .order_by(models.Invoice.date.desc())  # ترتيب من الأحدث للأقدم
        .offset(skip)  # تطبيق التجاوز
        .limit(limit)  # تطبيق الحد الأقصى
    )

    result = await db.execute(query)
    invoices = result.scalars().all()

    return invoices

@app.post("/api/expenses", response_model=schemas.ExpenseResponse)
async def add_expense(expense: schemas.ExpenseCreate, current_user: models.User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    db_expense = models.ExpenseRecord(**expense.dict(), owner_id=current_user.id)
    db.add(db_expense)
    await db.commit()
    await db.refresh(db_expense)
    return db_expense


@app.get("/api/summary", response_model=schemas.SummaryResponse)
async def get_summary(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # جلب الدخل
    income_query = select(func.sum(models.Invoice.net_total)).where(models.Invoice.owner_id == current_user.id)
    income_result = await db.execute(income_query)
    total_income = income_result.scalar() or 0.0

    # جلب المصاريف
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
async def get_crops(current_user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(models.InvoiceItem.crop_name).join(models.Invoice).where(
        models.Invoice.owner_id == current_user.id).distinct()
    result = await db.execute(query)
    crops = result.scalars().all()
    return list(crops)


@app.get("/api/crops/{crop_name}/history", response_model=schemas.CropHistoryResponse)
async def get_crop_history(crop_name: str, year: Optional[int] = None,
                           current_user: models.User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    query = select(models.InvoiceItem, models.Invoice.date).join(models.Invoice).where(
        models.InvoiceItem.crop_name == crop_name, models.Invoice.owner_id == current_user.id)

    if year: query = query.where(extract('year', models.Invoice.date) == year)
    query = query.order_by(models.Invoice.date.desc())

    result = await db.execute(query)
    items = result.all()  # بيرجع قائمة من الـ Tuples (InvoiceItem, date)

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
    # حذف الفواتير بالطريقة الصاروخية
    query = select(models.Invoice).where(models.Invoice.owner_id == current_user.id)
    result = await db.execute(query)
    invoices = result.scalars().all()

    for inv in invoices:
        await db.delete(inv)

        # حذف المصاريف بضربة وحدة
    stmt = delete(models.ExpenseRecord).where(models.ExpenseRecord.owner_id == current_user.id)
    await db.execute(stmt)

    await db.commit()
    return {"message": "User specific data wiped"}