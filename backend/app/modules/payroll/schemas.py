import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import LocalizedText


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class Installment(BaseModel):
    month: date
    amount: Decimal


class DeductionOut(BaseModel):
    id: str
    employee: dict | None
    company_id: int
    source_type: str
    reason: str
    total: Decimal
    installments: int
    start_month: date
    schedule: list[Installment]
    status: str
    created_at: datetime
    created_by: str | None
    cancelled_at: datetime | None
    cancelled_by: str | None
    cancel_reason: str | None


# ------------------------------------------------------------------ platforms

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
Header = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
DriverField = Literal["valid_days", "orders", "hours"]


class SheetColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str  # one of columns.COLUMNS (checked by the service)
    header: Header


class PlatformIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: LocalizedText
    driver_fields: list[DriverField] = Field(default_factory=list, max_length=3)
    pay_basic: bool = True
    per_order: Money = Decimal(0)
    per_hour: Money = Decimal(0)
    per_valid_day: Money = Decimal(0)
    invalid_days: Literal["none", "daily_wage", "fixed"] = "none"
    invalid_day_amount: Money | None = None
    day_divisor: int = Field(30, ge=1, le=31)
    columns: list[SheetColumn] = Field(default_factory=list, max_length=60)


class PlatformUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name: LocalizedText | None = None
    is_active: bool | None = None
    driver_fields: list[DriverField] | None = Field(None, max_length=3)
    pay_basic: bool | None = None
    per_order: Money | None = None
    per_hour: Money | None = None
    per_valid_day: Money | None = None
    invalid_days: Literal["none", "daily_wage", "fixed"] | None = None
    invalid_day_amount: Money | None = None
    day_divisor: int | None = Field(None, ge=1, le=31)
    columns: list[SheetColumn] | None = Field(None, max_length=60)


class PlatformOut(BaseModel):
    id: int
    public_id: str
    code: str
    name: dict[str, str]
    is_active: bool
    driver_fields: list[str]
    pay_basic: bool
    per_order: Decimal
    per_hour: Decimal
    per_valid_day: Decimal
    invalid_days: str
    invalid_day_amount: Decimal | None
    day_divisor: int
    columns: list[SheetColumn]
    drivers: int  # employees on this platform now
    version: int


class TemplateColumn(BaseModel):
    header: str
    code: str


class TemplateSheet(BaseModel):
    sheet: str
    suggested_name: str
    columns: list[TemplateColumn]
    driver_fields: list[str]
    invalid_days: str


# ------------------------------------------------------------------ monthly platform statements

Days = Annotated[int, Field(ge=0, le=31)]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class DriverStatementIn(BaseModel):
    """From the driver app: the month, the screenshots from the platform's app, and the figures read from them."""

    model_config = ConfigDict(extra="forbid")

    month: date  # any day of the month
    screenshots: list[Sha] = Field(min_length=1, max_length=6)
    valid_days: Days | None = None
    orders: int | None = Field(None, ge=0, le=20_000)
    hours: Decimal | None = Field(None, ge=0, le=744, max_digits=6, decimal_places=2)


class Figures(BaseModel):
    """What payroll uses from a statement: the platform's counts and the amounts from its settlement."""

    model_config = ConfigDict(extra="forbid")

    working_days: Days | None = None
    valid_days: Days | None = None
    orders: int | None = Field(None, ge=0, le=20_000)
    hours: Decimal | None = Field(None, ge=0, le=744, max_digits=6, decimal_places=2)
    bonus: Money = Decimal(0)
    tips: Money = Decimal(0)
    cancelled_orders: Money = Decimal(0)
    platform_deductions: Money = Decimal(0)
    late: Money = Decimal(0)
    cash_shortage: Money = Decimal(0)


class OfficeStatementIn(Figures):
    """Entered by the office (no screenshot from the driver): approved at once."""

    employee_id: uuid.UUID
    month: date
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ApproveStatementIn(Figures):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class StatementOut(BaseModel):
    id: str
    employee: dict | None
    company_id: int
    platform: dict | None
    month: date
    status: str
    declared: dict
    working_days: int | None
    valid_days: int | None
    orders: int | None
    hours: Decimal | None
    bonus: Decimal
    tips: Decimal
    cancelled_orders: Decimal
    platform_deductions: Decimal
    late: Decimal
    cash_shortage: Decimal
    screenshots: list[str]
    system: dict  # what the system itself counted for the month (days worked, orders reported), to compare
    submitted_at: datetime
    from_driver: bool
    reviewed_at: datetime | None
    reviewed_by: str | None
    review_note: str | None
    locked: bool  # the month's payroll is approved: nothing changes any more
    version: int


class DriverStatementOut(BaseModel):
    id: str
    month: date
    status: str
    declared: dict
    valid_days: int | None
    orders: int | None
    hours: Decimal | None
    review_note: str | None
    submitted_at: datetime


class DriverPlatformOut(BaseModel):
    """What the app needs to ask for the monthly statement."""

    platform: dict | None
    driver_fields: list[str]
    months: list[date]  # the months a statement can be sent for now
    statements: list[DriverStatementOut]


# ------------------------------------------------------------------ manual deductions (advance, SIM card, other)


class DeductionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: uuid.UUID
    source_type: Literal["advance", "sim", "other"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    total: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
    installments: int = Field(1, ge=1, le=60)
    start_month: date | None = None  # next month when omitted


# ------------------------------------------------------------------ payroll runs


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    month: date  # any day of the month


class ReopenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class PaidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_ref: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class LineOut(BaseModel):
    employee: dict
    platform_id: int | None
    cells: dict
    gross: Decimal
    deductions: Decimal
    net: Decimal
    flags: list[str]
    statement_id: str | None


class RunOut(BaseModel):
    id: str
    company_id: int
    month: date
    status: str
    cap_percent: Decimal
    cap_base: str
    totals: dict
    prepared_at: datetime
    prepared_by: str | None
    approved_at: datetime | None
    approved_by: str | None
    paid_at: datetime | None
    paid_by: str | None
    payment_ref: str | None
    reopened: int
    blocking: int  # lines that stop the approval
    version: int


class RunDetail(RunOut):
    lines: list[LineOut]


class PayslipOut(BaseModel):
    month: date
    status: str  # approved | paid
    platform: dict | None
    rows: list[dict]  # [{code, header, value}] in the platform's sheet order, the employee's identity left out
    gross: Decimal
    deductions: Decimal
    net: Decimal
