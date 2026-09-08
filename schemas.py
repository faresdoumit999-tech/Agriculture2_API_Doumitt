from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from pydantic import ConfigDict
from pydantic import field_validator
from pydantic import BaseModel, Field, ConfigDict
# --- Auth Schemas ---

class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8, description="يجب ألا تقل كلمة المرور عن 8 أحرف")


class Token(BaseModel):
    access_token: str
    token_type: str


# --- App Schemas ---
class InvoiceItemBase(BaseModel):
    crop_name: str
    box_count: int = Field(gt=0, description="عدد الصناديق يجب أن يكون أكبر من الصفر")
    net_weight: float = Field(gt=0, description="الوزن الصافي يجب أن يكون أكبر من الصفر")
    unit_price: float = Field(gt=0, description="السعر يجب أن يكون أكبر من الصفر")
    subtotal: float


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemResponse(InvoiceItemBase):
    id: int
    invoice_id: int

    model_config = ConfigDict(from_attributes=True)


class InvoiceBase(BaseModel):
    date: date
    total_gross: float = Field(ge=0)
    deductions: float = Field(ge=0)
    net_total: float


class InvoiceCreate(InvoiceBase):
    items: List[InvoiceItemCreate]


class InvoiceResponse(InvoiceBase):
    id: int
    items: List[InvoiceItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ExpenseBase(BaseModel):
    date: date
    category: str
    description: str
    amount: float = Field(gt=0, description="المبلغ يجب أن يكون أكبر من الصفر")


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseResponse(ExpenseBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


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