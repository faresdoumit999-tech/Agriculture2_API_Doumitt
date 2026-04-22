from fastapi import FastAPI, Depends, Request, Query
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date
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

@app.post("/api/invoices/bulk", response_model=List[schemas.InvoiceResponse])
def add_invoices_bulk(invoices: List[schemas.InvoiceCreate], db: Session = Depends(get_db)):
    db_invoices = []
    for invoice in invoices:
        db_invoice = models.Invoice(
            date=invoice.date,
            total_gross=invoice.total_gross,
            deductions=invoice.deductions,
            net_total=invoice.net_total
        )
        db.add(db_invoice)
        db.flush() # To get the id
        
        for item in invoice.items:
            db_item = models.InvoiceItem(**item.dict(), invoice_id=db_invoice.id)
            db.add(db_item)
            
        db_invoices.append(db_invoice)
        
    db.commit()
    for inv in db_invoices:
        db.refresh(inv)
    return db_invoices

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

@app.get("/api/reports/summary", response_model=schemas.ReportSummaryResponse)
def get_reports_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    crop_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(
        func.sum(models.Invoice.total_gross).label("total_gross"),
        func.sum(models.Invoice.deductions).label("total_deductions"),
        func.sum(models.Invoice.net_total).label("total_net"),
        func.sum(models.InvoiceItem.net_weight).label("total_weight")
    ).join(models.InvoiceItem)
    
    if start_date:
        query = query.filter(models.Invoice.date >= start_date)
    if end_date:
        query = query.filter(models.Invoice.date <= end_date)
    if crop_name and crop_name != "الكل":
        query = query.filter(models.InvoiceItem.crop_name == crop_name)
        
    result = query.first()
    
    return schemas.ReportSummaryResponse(
        total_gross=result.total_gross or 0.0,
        total_deductions=result.total_deductions or 0.0,
        total_net=result.total_net or 0.0,
        total_weight=result.total_weight or 0.0
    )

@app.get("/api/crops", response_model=list[str])
def get_crops(db: Session = Depends(get_db)):
    crops = db.query(models.InvoiceItem.crop_name).distinct().all()
    return [crop[0] for crop in crops]

@app.get("/api/crops/{crop_name}/history", response_model=schemas.CropHistoryResponse)
def get_crop_history(crop_name: str, db: Session = Depends(get_db)):
    items = db.query(models.InvoiceItem, models.Invoice.date).join(models.Invoice).filter(models.InvoiceItem.crop_name == crop_name).order_by(models.Invoice.date.desc()).all()
    
    history_list = []
    total_weight = 0.0
    total_revenue = 0.0
    
    for item, inv_date in items:
        history_list.append(schemas.CropHistoryItem(
            invoice_date=inv_date,
            box_count=item.box_count,
            net_weight=item.net_weight,
            unit_price=item.unit_price,
            subtotal=item.subtotal
        ))
        total_weight += item.net_weight
        total_revenue += item.subtotal
        
    return schemas.CropHistoryResponse(
        crop_name=crop_name,
        history=history_list, # Pydantic handles date serialization
        total_weight=total_weight,
        total_revenue=total_revenue
    )

@app.delete("/api/reset")
def reset_database(db: Session = Depends(get_db)):
    db.query(models.InvoiceItem).delete()
    db.query(models.Invoice).delete()
    db.query(models.ExpenseRecord).delete()
    db.commit()
    return {"message": "Database reset successfully"}
