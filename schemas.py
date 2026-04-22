from pydantic import BaseModel
from datetime import date
from typing import List, Optional

class InvoiceItemBase(BaseModel):
    crop_name: str
    box_count: int
    net_weight: float
    unit_price: float
    subtotal: float

class InvoiceItemCreate(InvoiceItemBase):
    pass

class InvoiceItemResponse(InvoiceItemBase):
    id: int
    invoice_id: int

    class Config:
        from_attributes = True

class InvoiceBase(BaseModel):
    date: date
    total_gross: float
    deductions: float
    net_total: float

class InvoiceCreate(InvoiceBase):
    items: List[InvoiceItemCreate]

class InvoiceResponse(InvoiceBase):
    id: int
    items: List[InvoiceItemResponse]

    class Config:
        from_attributes = True

class ExpenseBase(BaseModel):
    date: date
    category: str
    description: str
    amount: float

class ExpenseCreate(ExpenseBase):
    pass

class ExpenseResponse(ExpenseBase):
    id: int

    class Config:
        from_attributes = True

class SummaryResponse(BaseModel):
    total_income: float
    total_expenses: float
    net_profit: float

class ReportSummaryResponse(BaseModel):
    total_gross: float
    total_deductions: float
    total_net: float
    total_weight: float

class CropHistoryItem(BaseModel):
    invoice_date: date
    box_count: int
    net_weight: float
    unit_price: float
    subtotal: float

class CropHistoryResponse(BaseModel):
    crop_name: str
    history: List[CropHistoryItem]
    total_weight: float
    total_revenue: float
