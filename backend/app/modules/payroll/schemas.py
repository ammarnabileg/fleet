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
DailyField = Literal["orders", "cash", "valid_day"]


class SheetColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str  # one of columns.COLUMNS (checked by the service)
    header: Header


class PlatformIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: LocalizedText
    driver_fields: list[DriverField] = Field(default_factory=list, max_length=3)
    daily_fields: list[DailyField] = Field(default_factory=lambda: ["orders", "cash"], max_length=3)
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
    daily_fields: list[DailyField] | None = Field(None, max_length=3)
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
    daily_fields: list[str]
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
    # what a pay scheme needs, from the platform's partner report
    batch_level: int | None = Field(None, ge=1, le=20)
    attendance_marks: int | None = Field(None, ge=0, le=31)
    star_day_failed: bool | None = None
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
    batch_level: int | None
    attendance_marks: int | None
    star_day_failed: bool | None
    bonus: Decimal
    tips: Decimal
    cancelled_orders: Decimal
    platform_deductions: Decimal
    late: Decimal
    cash_shortage: Decimal
    screenshots: list[str]
    system: dict  # what the system itself counted for the month (days worked, orders reported), to compare
    scheme: dict | None = None  # the driver's pay scheme that month, and the figures it needs (detail only)
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
    breakdown: list[dict] = []  # a pay scheme's items: orders, tier bonus, penalties, with why


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
    scheme: dict | None = None  # {name} of his pay scheme that month
    breakdown: list[dict] = []  # [{code, amount, why}]: how the scheme computed the month
    gross: Decimal
    deductions: Decimal
    net: Decimal


# ------------------------------------------------------------------ pay schemes

CalculatorCode = Literal["platform_rates", "per_order", "batch", "tiered_target"]
StepKind = Literal["batch_rate", "tier_bonus", "marks_deduction", "marks_reduce"]
Cover = Literal["maintenance", "housing", "gas", "sim"]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class SchemeStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: StepKind
    threshold: Annotated[Decimal, Field(ge=0, le=100_000, max_digits=12, decimal_places=3)]
    amount: Money | None = None  # none for marks_reduce (the scheme's reduced price applies)


class SchemeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_id: int
    code: Code
    name: LocalizedText
    description: LocalizedText | None = None
    calculator: CalculatorCode
    per_order: Money | None = None
    target_orders: int = Field(420, ge=0, le=100_000)
    required_valid_days: int = Field(28, ge=0, le=31)
    missing_order_rate: Money | None = None
    reduced_rate: Money | None = None
    bonus_when_reduced: bool = False
    marks_when_reduced: bool = False
    floor_at_zero: bool = True
    company_covers: list[Cover] = Field(default_factory=list, max_length=4)
    driver_selectable: bool = True
    steps: list[SchemeStepIn] = Field(default_factory=list, max_length=50)


class SchemeUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name: LocalizedText | None = None
    description: LocalizedText | None = None
    is_active: bool | None = None
    driver_selectable: bool | None = None
    # what drivers are paid on: refused once a driver is on the scheme (a new price is a new scheme)
    calculator: CalculatorCode | None = None
    per_order: Money | None = None
    target_orders: int | None = Field(None, ge=0, le=100_000)
    required_valid_days: int | None = Field(None, ge=0, le=31)
    missing_order_rate: Money | None = None
    reduced_rate: Money | None = None
    bonus_when_reduced: bool | None = None
    marks_when_reduced: bool | None = None
    floor_at_zero: bool | None = None
    company_covers: list[Cover] | None = Field(None, max_length=4)
    steps: list[SchemeStepIn] | None = Field(None, max_length=50)


class SchemeOut(BaseModel):
    id: str
    platform_id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    calculator: str
    per_order: Decimal | None
    target_orders: int
    required_valid_days: int
    missing_order_rate: Decimal | None
    reduced_rate: Decimal | None
    bonus_when_reduced: bool
    marks_when_reduced: bool
    floor_at_zero: bool
    company_covers: list[str]
    driver_selectable: bool
    is_active: bool
    steps: list[dict]
    drivers: int  # on it this month
    version: int


class AssignSchemeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    month: date  # from this month on


class AssignSchemeOut(BaseModel):
    set: int
    skipped: list[dict]
    from_: date = Field(alias="from")

    model_config = ConfigDict(populate_by_name=True)


class SchemeHistoryOut(BaseModel):
    scheme: dict
    valid_from: date
    valid_to: date | None
    source: str
    set_at: datetime


class SchemeRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme_id: uuid.UUID
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class SchemeRequestOut(BaseModel):
    id: str
    employee: dict | None
    company_id: int
    current: dict | None
    requested: dict | None
    effective_month: date
    status: str
    driver_note: str | None
    admin_note: str | None
    created_at: datetime
    decided_at: datetime | None
    version: int


class DriverSchemeOut(BaseModel):
    """A scheme's terms as the driver reads them: not how many drivers are on it, nor the office's flags."""

    id: str
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    calculator: str
    per_order: Decimal | None
    target_orders: int
    required_valid_days: int
    missing_order_rate: Decimal | None
    reduced_rate: Decimal | None
    bonus_when_reduced: bool
    marks_when_reduced: bool
    floor_at_zero: bool
    company_covers: list[str]
    steps: list[dict]


class DriverSchemesOut(BaseModel):
    current: DriverSchemeOut | None  # this month
    next_month: DriverSchemeOut | None  # when it changes next month
    schemes: list[DriverSchemeOut]  # what his platform offers
    request: SchemeRequestOut | None  # his latest request


class ApproveSchemeRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    month: date | None = None  # later than asked, never earlier
    note: Note | None = None


class RejectSchemeRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    note: Note  # the driver reads why
