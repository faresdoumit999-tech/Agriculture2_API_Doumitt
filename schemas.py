"""Pydantic v2 request/response schemas."""

from datetime import date as Date
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Currency = Literal["USD", "SYP"]
ExpenseNature = Literal["SEASONAL", "DAILY"]
ExpenseCategory = Literal[
    "POLYSTYRENE", "VEHICLE_FUEL", "PESTICIDE", "FERTILIZER", "SETUP", "OTHER"
]
SHARECROPPER_CATEGORIES: tuple[str, ...] = ("POLYSTYRENE", "VEHICLE_FUEL")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=6, max_length=72)
    phone_number: str | None = Field(default=None, max_length=30)


class UserRead(ORMModel):
    id: int
    username: str
    phone_number: str | None
    role: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    success: bool = True
    message: str


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    greenhouse_count: int = Field(default=1, ge=1, le=10000)
    crops_planted: str | None = Field(default=None, max_length=500)
    season_start_date: Date
    season_end_date: Date | None = None
    is_active: bool = True
    has_sharecropper: bool = False
    sharecropper_name: str | None = Field(default=None, max_length=150)
    sharecropper_profit_pct: float = Field(default=0.0, ge=0, le=100)
    sharecropper_expense_pct: float = Field(default=0.0, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_dates(self) -> "ProjectBase":
        if self.season_end_date and self.season_end_date < self.season_start_date:
            raise ValueError("تاريخ نهاية الموسم يجب أن يكون بعد تاريخ البداية.")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    greenhouse_count: int | None = Field(default=None, ge=1, le=10000)
    crops_planted: str | None = Field(default=None, max_length=500)
    season_start_date: Date | None = None
    season_end_date: Date | None = None
    is_active: bool | None = None
    has_sharecropper: bool | None = None
    sharecropper_name: str | None = Field(default=None, max_length=150)
    sharecropper_profit_pct: float | None = Field(default=None, ge=0, le=100)
    sharecropper_expense_pct: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_dates(self) -> "ProjectUpdate":
        if (
            self.season_start_date
            and self.season_end_date
            and self.season_end_date < self.season_start_date
        ):
            raise ValueError("تاريخ نهاية الموسم يجب أن يكون بعد تاريخ البداية.")
        return self


class ProjectRead(ORMModel):
    id: int
    owner_id: int
    name: str
    greenhouse_count: int
    crops_planted: str | None
    season_start_date: Date
    season_end_date: Date | None
    is_active: bool
    has_sharecropper: bool
    sharecropper_name: str | None
    sharecropper_profit_pct: float
    sharecropper_expense_pct: float
    notes: str | None


class ProjectFinancialSummary(BaseModel):
    invoice_count: int = 0
    expense_count: int = 0
    total_expenses_usd: float = 0.0
    total_expenses_syp: float = 0.0
    total_gross_sales_usd: float = 0.0
    total_gross_sales_syp: float = 0.0
    total_sales_usd: float = 0.0
    total_sales_syp: float = 0.0
    sharecropper_due_usd: float = 0.0
    sharecropper_due_syp: float = 0.0
    net_profit_usd: float = 0.0
    net_profit_syp: float = 0.0
    cost_per_greenhouse_usd: float = 0.0
    revenue_per_greenhouse_usd: float = 0.0
    profit_per_greenhouse_usd: float = 0.0
    cost_per_greenhouse_syp: float = 0.0
    revenue_per_greenhouse_syp: float = 0.0
    profit_per_greenhouse_syp: float = 0.0


class ProjectWithSummary(ProjectRead):
    financials: ProjectFinancialSummary


# ---------------------------------------------------------------------------
# Warehouse
# ---------------------------------------------------------------------------


class WarehouseItemCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    pharmacy_name: str = Field(min_length=1, max_length=200)
    purchase_date: Date
    quantity: float = Field(gt=0, description="الكمية المشتراة وتقبل الفواصل العشرية")
    unit: str = Field(default="لتر/عبوة", min_length=1, max_length=50)
    currency: Currency
    unit_price: float = Field(gt=0)
    exchange_rate: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_currency(self) -> "WarehouseItemCreate":
        if self.currency == "USD" and self.exchange_rate is None:
            raise ValueError("سعر الصرف مطلوب عند الشراء بالدولار.")
        return self


class WarehouseItemUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    pharmacy_name: str | None = Field(default=None, min_length=1, max_length=200)
    purchase_date: Date | None = None
    initial_quantity: float | None = Field(default=None, gt=0)
    remaining_quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    currency: Currency | None = None
    unit_price: float | None = Field(default=None, gt=0)
    exchange_rate: float | None = Field(default=None, ge=0)


class WarehouseItemRead(ORMModel):
    id: int
    owner_id: int
    product_name: str
    pharmacy_name: str
    purchase_date: Date
    initial_quantity: float
    remaining_quantity: float
    unit: str
    currency: str
    exchange_rate: float
    unit_price_usd: float
    unit_price_syp: float
    total_cost_usd: float
    total_cost_syp: float
    consumed_quantity: float = 0.0
    stock_status: str = "ok"


class ConsumeRequest(BaseModel):
    warehouse_item_id: int
    project_id: int
    quantity_used: float = Field(gt=0, examples=[0.25])
    date: Date
    category: ExpenseCategory = "PESTICIDE"
    expense_nature: ExpenseNature = "DAILY"
    enters_sharecropper_calc: bool | None = None
    custom_sharecropper_pct: float | None = Field(default=None, ge=0, le=100)


class ConsumeResponse(BaseModel):
    expense: "ExpenseRead"
    warehouse_item: WarehouseItemRead


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


class ExpenseCreate(BaseModel):
    project_id: int
    date: Date
    expense_nature: ExpenseNature
    category: ExpenseCategory
    item_name: str = Field(min_length=1, max_length=200)
    pharmacy_name: str | None = Field(default=None, max_length=200)
    quantity_used: float = Field(default=1.0, gt=0)
    unit_price: float = Field(ge=0)
    currency: Currency
    exchange_rate: float | None = Field(default=None, gt=0)
    enters_sharecropper_calc: bool | None = None
    custom_sharecropper_pct: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_currency(self) -> "ExpenseCreate":
        if self.currency == "USD" and self.exchange_rate is None:
            raise ValueError("سعر الصرف مطلوب عند تسجيل المصروف بالدولار.")
        return self


class ExpenseUpdate(BaseModel):
    project_id: int | None = None
    date: Date | None = None
    expense_nature: ExpenseNature | None = None
    category: ExpenseCategory | None = None
    item_name: str | None = Field(default=None, min_length=1, max_length=200)
    pharmacy_name: str | None = Field(default=None, max_length=200)
    quantity_used: float | None = Field(default=None, gt=0)
    unit_price: float | None = Field(default=None, ge=0)
    currency: Currency | None = None
    exchange_rate: float | None = Field(default=None, ge=0)
    enters_sharecropper_calc: bool | None = None
    custom_sharecropper_pct: float | None = Field(default=None, ge=0, le=100)


class ExpenseRead(ORMModel):
    id: int
    owner_id: int
    project_id: int
    warehouse_item_id: int | None
    date: Date
    expense_nature: str
    category: str
    item_name: str
    pharmacy_name: str | None
    quantity_used: float
    unit_price: float
    currency: str
    exchange_rate: float
    total_amount_usd: float
    total_amount_syp: float
    enters_sharecropper_calc: bool
    custom_sharecropper_pct: float | None
    sharecropper_deduction_usd: float
    sharecropper_deduction_syp: float


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


class InvoiceItemCreate(BaseModel):
    crop_name: str = Field(min_length=1, max_length=150)
    box_count: int = Field(default=0, ge=0)
    gross_weight: float = Field(default=0.0, ge=0)
    net_weight: float = Field(ge=0)
    unit_price: float = Field(ge=0)


class InvoiceItemRead(ORMModel):
    id: int
    crop_name: str
    box_count: int
    gross_weight: float
    net_weight: float
    unit_price: float
    subtotal: float


class InvoiceCreate(BaseModel):
    project_id: int
    date: Date
    currency: Currency = "SYP"
    exchange_rate: float | None = Field(default=None, gt=0)
    commission_amount: float = Field(default=0.0, ge=0)
    polystyrene_expense: float = Field(default=0.0, ge=0)
    vehicle_fuel_expense: float = Field(default=0.0, ge=0)
    other_deductions: float = Field(default=0.0, ge=0)
    items: list[InvoiceItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_currency(self) -> "InvoiceCreate":
        if self.currency == "USD" and self.exchange_rate is None:
            raise ValueError("سعر الصرف مطلوب عند إدخال الفاتورة بالدولار.")
        return self


class InvoiceUpdate(BaseModel):
    project_id: int | None = None
    date: Date | None = None
    currency: Currency | None = None
    exchange_rate: float | None = Field(default=None, ge=0)
    commission_amount: float | None = Field(default=None, ge=0)
    polystyrene_expense: float | None = Field(default=None, ge=0)
    vehicle_fuel_expense: float | None = Field(default=None, ge=0)
    other_deductions: float | None = Field(default=None, ge=0)
    items: list[InvoiceItemCreate] | None = Field(default=None, min_length=1)


class InvoiceRead(ORMModel):
    id: int
    owner_id: int
    project_id: int
    date: Date
    currency: str
    exchange_rate: float
    total_gross: float
    commission_amount: float
    polystyrene_expense: float
    vehicle_fuel_expense: float
    other_deductions: float
    net_total: float
    net_total_usd: float
    net_total_syp: float
    sharecropper_applied_profit_pct: float
    sharecropper_applied_expense_pct: float
    sharecropper_gross_share_syp: float
    sharecropper_expense_deduction_syp: float
    sharecropper_net_payout_syp: float
    sharecropper_net_payout_usd: float
    owner_net_profit_syp: float
    owner_net_profit_usd: float
    items: list[InvoiceItemRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class ProjectInfo(BaseModel):
    id: int
    name: str
    greenhouse_count: int
    crops_planted: str | None
    season_start_date: Date
    season_end_date: Date | None
    is_active: bool
    has_sharecropper: bool
    sharecropper_name: str | None
    sharecropper_profit_pct: float
    sharecropper_expense_pct: float


class CategoryBreakdown(BaseModel):
    category: str
    label: str
    total_usd: float
    total_syp: float
    share_pct: float


class PesticideUsage(BaseModel):
    date: Date
    item_name: str
    pharmacy_name: str | None
    quantity_used: float
    unit: str
    total_usd: float
    total_syp: float


class ExpenseBreakdown(BaseModel):
    seasonal_usd: float
    seasonal_syp: float
    daily_usd: float
    daily_syp: float
    total_usd: float
    total_syp: float
    by_category: list[CategoryBreakdown]
    pesticide_usage: list[PesticideUsage]


class CropBreakdown(BaseModel):
    crop_name: str
    net_weight: float
    gross_weight: float
    box_count: int
    revenue_usd: float
    revenue_syp: float
    share_pct: float


class SalesBreakdown(BaseModel):
    invoice_count: int
    gross_weight: float
    net_weight: float
    box_count: int
    total_gross_usd: float
    total_gross_syp: float
    commission_usd: float
    commission_syp: float
    polystyrene_usd: float
    polystyrene_syp: float
    vehicle_fuel_usd: float
    vehicle_fuel_syp: float
    other_deductions_usd: float
    other_deductions_syp: float
    net_sales_usd: float
    net_sales_syp: float
    by_crop: list[CropBreakdown]


class SharecropperStatement(BaseModel):
    enabled: bool
    name: str | None
    profit_pct: float
    expense_pct: float
    gross_share_usd: float
    gross_share_syp: float
    invoice_expense_deduction_usd: float
    invoice_expense_deduction_syp: float
    separate_expense_deduction_usd: float
    separate_expense_deduction_syp: float
    total_deductions_usd: float
    total_deductions_syp: float
    net_payout_usd: float
    net_payout_syp: float


class GreenhouseMetrics(BaseModel):
    greenhouse_count: int
    cost_usd: float
    cost_syp: float
    revenue_usd: float
    revenue_syp: float
    net_profit_usd: float
    net_profit_syp: float


class NetProfitSummary(BaseModel):
    expenses_usd: float
    expenses_syp: float
    sales_net_usd: float
    sales_net_syp: float
    sharecropper_payout_usd: float
    sharecropper_payout_syp: float
    owner_net_profit_usd: float
    owner_net_profit_syp: float
    margin_pct: float


class FullAuditReport(BaseModel):
    project: ProjectInfo
    expenses: ExpenseBreakdown
    sales: SalesBreakdown
    sharecropper: SharecropperStatement
    per_greenhouse_metrics: GreenhouseMetrics
    net_profit: NetProfitSummary
    generated_at: datetime


class ProjectComparison(BaseModel):
    id: int
    name: str
    greenhouse_count: int
    is_active: bool
    expenses_usd: float
    expenses_syp: float
    sales_usd: float
    sales_syp: float
    net_profit_usd: float
    net_profit_syp: float
    profit_per_greenhouse_usd: float


class GlobalTotals(BaseModel):
    expenses_usd: float
    expenses_syp: float
    sales_usd: float
    sales_syp: float
    sharecropper_dues_usd: float
    sharecropper_dues_syp: float
    net_profit_usd: float
    net_profit_syp: float


class GlobalSummary(BaseModel):
    projects_count: int
    active_projects: int
    total_greenhouses: int
    totals: GlobalTotals
    projects: list[ProjectComparison]
    most_profitable: ProjectComparison | None
    most_costly: ProjectComparison | None


class CropHistoryPoint(BaseModel):
    date: Date
    invoice_id: int
    project_id: int
    project_name: str
    net_weight: float
    unit_price: float
    revenue_usd: float
    revenue_syp: float


class CropHistoryResponse(BaseModel):
    crop_name: str
    points: list[CropHistoryPoint]
    total_net_weight: float
    total_revenue_usd: float
    total_revenue_syp: float


class TaskAccepted(BaseModel):
    task_id: str
    status: str = "PENDING"
    message: str


ConsumeResponse.model_rebuild()
