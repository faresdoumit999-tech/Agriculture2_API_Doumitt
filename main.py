from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import models, schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="DOUMITT")

templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/invoices", response_model=schemas.InvoiceResponse)
def add_invoice(invoice: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    db_invoice = models.Invoice(
        date=invoice.date,
        total_gross=invoice.total_gross,
        deductions=invoice.deductions,
        net_total=invoice.net_total
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)

    for item in invoice.items:
        db_item = models.InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
        db.add(db_item)
    
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@app.post("/api/expenses", response_model=schemas.ExpenseResponse)
def add_expense(expense: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    db_expense = models.ExpenseRecord(**expense.dict())
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@app.get("/api/invoices", response_model=list[schemas.InvoiceResponse])
def get_invoices(db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    return db.query(models.Invoice).order_by(models.Invoice.id.desc()).offset(skip).limit(limit).all()

@app.get("/api/expenses", response_model=list[schemas.ExpenseResponse])
def get_expenses(db: Session = Depends(get_db), skip: int = 0, limit: int = 20):
    return db.query(models.ExpenseRecord).order_by(models.ExpenseRecord.id.desc()).offset(skip).limit(limit).all()

@app.get("/api/summary", response_model=schemas.SummaryResponse)
def get_summary(db: Session = Depends(get_db)):
    total_income = db.query(func.sum(models.Invoice.net_total)).scalar() or 0.0
    total_expenses = db.query(func.sum(models.ExpenseRecord.amount)).scalar() or 0.0
    net_profit = total_income - total_expenses
    return schemas.SummaryResponse(
        total_income=total_income,
        total_expenses=total_expenses,
        net_profit=net_profit
    )

@app.get("/api/crops", response_model=list[str])
def get_crops(db: Session = Depends(get_db)):
    crops = db.query(models.InvoiceItem.crop_name).distinct().all()
    return [crop[0] for crop in crops]

@app.delete("/api/reset")
def reset_database(db: Session = Depends(get_db)):
    db.query(models.InvoiceItem).delete()
    db.query(models.Invoice).delete()
    db.query(models.ExpenseRecord).delete()
    db.commit()
    return {"message": "Database reset successfully"}
