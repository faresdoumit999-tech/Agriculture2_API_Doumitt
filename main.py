from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Optional
from datetime import date, datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt

import models, schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="DOUMITT SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=[False],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None: raise credentials_exception
    return user


# ==========================================
# 🚪 مسارات تسجيل الدخول والاشتراك
# ==========================================
@app.post("/api/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="اسم المستخدم محجوز مسبقاً")
    hashed_pwd = get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    access_token = create_access_token(data={"sub": new_user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


# ==========================================
# 📊 مسارات النظام (معزولة لكل مستخدم)
# ==========================================
@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/invoices", response_model=schemas.InvoiceResponse)
def add_invoice(invoice: schemas.InvoiceCreate, current_user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    db_invoice = models.Invoice(date=invoice.date, total_gross=invoice.total_gross, deductions=invoice.deductions,
                                net_total=invoice.net_total, owner_id=current_user.id)
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)

    for item in invoice.items:
        db_item = models.InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
        db.add(db_item)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice


@app.post("/api/invoices/bulk", response_model=List[schemas.InvoiceResponse])
def add_invoices_bulk(invoices: List[schemas.InvoiceCreate], current_user: models.User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    db_invoices = []
    for invoice in invoices:
        db_invoice = models.Invoice(date=invoice.date, total_gross=invoice.total_gross, deductions=invoice.deductions,
                                    net_total=invoice.net_total, owner_id=current_user.id)
        db.add(db_invoice)
        db.flush()
        for item in invoice.items:
            db_item = models.InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
            db.add(db_item)
        db_invoices.append(db_invoice)
    db.commit()
    for inv in db_invoices: db.refresh(inv)
    return db_invoices


@app.post("/api/expenses", response_model=schemas.ExpenseResponse)
def add_expense(expense: schemas.ExpenseCreate, current_user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    db_expense = models.ExpenseRecord(**expense.dict(), owner_id=current_user.id)
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense


@app.get("/api/summary", response_model=schemas.SummaryResponse)
def get_summary(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_income = db.query(func.sum(models.Invoice.net_total)).filter(
        models.Invoice.owner_id == current_user.id).scalar() or 0.0
    total_expenses = db.query(func.sum(models.ExpenseRecord.amount)).filter(
        models.ExpenseRecord.owner_id == current_user.id).scalar() or 0.0
    net_profit = total_income - total_expenses
    return schemas.SummaryResponse(total_income=total_income, total_expenses=total_expenses, net_profit=net_profit)


@app.get("/api/reports/summary", response_model=schemas.ReportSummaryResponse)
def get_reports_summary(start_date: Optional[date] = None, end_date: Optional[date] = None,
                        crop_name: Optional[str] = None, current_user: models.User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    query = db.query(
        func.sum(models.Invoice.total_gross).label("total_gross"),
        func.sum(models.Invoice.deductions).label("total_deductions"),
        func.sum(models.Invoice.net_total).label("total_net"),
        func.sum(models.InvoiceItem.net_weight).label("total_weight")
    ).join(models.InvoiceItem).filter(models.Invoice.owner_id == current_user.id)

    if start_date: query = query.filter(models.Invoice.date >= start_date)
    if end_date: query = query.filter(models.Invoice.date <= end_date)
    if crop_name and crop_name != "الكل": query = query.filter(models.InvoiceItem.crop_name == crop_name)

    result = query.first()
    return schemas.ReportSummaryResponse(total_gross=result.total_gross or 0.0,
                                         total_deductions=result.total_deductions or 0.0,
                                         total_net=result.total_net or 0.0, total_weight=result.total_weight or 0.0)


@app.get("/api/crops", response_model=list[str])
def get_crops(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    crops = db.query(models.InvoiceItem.crop_name).join(models.Invoice).filter(
        models.Invoice.owner_id == current_user.id).distinct().all()
    return [crop[0] for crop in crops]


@app.get("/api/crops/{crop_name}/history", response_model=schemas.CropHistoryResponse)
def get_crop_history(crop_name: str, year: Optional[int] = None, current_user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    query = db.query(models.InvoiceItem, models.Invoice.date).join(models.Invoice).filter(
        models.InvoiceItem.crop_name == crop_name, models.Invoice.owner_id == current_user.id)
    if year: query = query.filter(extract('year', models.Invoice.date) == year)
    items = query.order_by(models.Invoice.date.desc()).all()

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
def reset_database(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.query(models.Invoice).filter(models.Invoice.owner_id == current_user.id).all()
    for inv in invoices: db.delete(inv)  # Cascades to items automatically
    db.query(models.ExpenseRecord).filter(models.ExpenseRecord.owner_id == current_user.id).delete()
    db.commit()
    return {"message": "User specific data wiped"}