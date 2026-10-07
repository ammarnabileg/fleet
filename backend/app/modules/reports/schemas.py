from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Dashboard(BaseModel):
    """A section is absent when the user lacks its permission."""

    model_config = ConfigDict(extra="allow")

    as_of: datetime
    alerts: dict[str, int]
    vehicles: dict[str, int] | None = None
    drivers: dict | None = None
    daily_reports: dict | None = None
    cash: dict | None = None
    documents: dict[str, int] | None = None
    maintenance: dict[str, int] | None = None
    accidents: dict[str, int] | None = None
    fines: dict[str, int | str] | None = None
    week: list[dict] | None = None  # the last seven days' reports, orders and cash, oldest first
    alerts_oldest: datetime | None = None  # the longest open alert (FR-DSH-07)
    approvals: dict | None = None  # waiting for this user's decision, and since when
    hr: dict | None = None  # employees by status, this month's payroll (FR-DSH-06)
    by_company: list[dict] | None = None  # one row per company when the user sees several (FR-CMP-03)


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class SummaryRow(BaseModel):
    driver: PersonRef
    employee_number: str
    company_id: int
    days: int
    orders: int
    reported_cash: Decimal
    approved_cash: Decimal
    waiting: int
    rejected: int
    late: int  # sent after their own day


class SummaryOut(BaseModel):
    from_: date = Field(alias="from")
    to: date
    rows: list[SummaryRow]
    totals: dict
    by_day: list[dict]  # sent, late, rejected, orders and cash per day of the period (FR-RPT-02)
    by_company: list[dict]

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


# ---- maintenance and accidents reports


class CenterLine(BaseModel):
    center: dict
    received: int
    still_there: int
    avg_stay_seconds: int | None
    max_stay_seconds: int | None
    invoices: int
    cost: Decimal
    avg_cost: Decimal | None


class VehicleCostLine(BaseModel):
    vehicle: dict
    times_received: int
    stay_seconds: int
    invoices: int
    cost: Decimal


class PartLine(BaseModel):
    description: str
    quantity: Decimal
    amount: Decimal
    invoices: int


class MaintenanceReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    totals: dict
    by_center: list[CenterLine]
    by_vehicle: list[VehicleCostLine]
    parts: list[PartLine]


class AccidentLine(BaseModel):
    id: str
    number: int
    occurred_at: datetime
    vehicle: dict | None
    driver: dict | None
    injuries: bool
    liability: str | None
    liability_percent: Decimal | None
    has_police_report: bool
    estimate: Decimal | None
    actual_cost: Decimal | None
    difference: Decimal | None
    deduction: Decimal | None
    status: str


class AccidentGroup(BaseModel):
    model_config = ConfigDict(extra="allow")  # "driver" or "vehicle"

    accidents: int
    liable: int
    estimate: Decimal
    actual_cost: Decimal
    deduction: Decimal


class WaitingLine(BaseModel):
    id: str
    number: int
    occurred_at: datetime
    vehicle: dict | None
    driver: dict | None
    days: int


class AccidentsReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    totals: dict
    by_outcome: dict[str, int]
    by_driver: list[AccidentGroup]
    by_vehicle: list[AccidentGroup]
    accidents: list[AccidentLine]
    waiting_police_report: list[WaitingLine]


class KmVehicle(BaseModel):
    vehicle: dict | None
    km: int
    on_duty: int
    off_duty: int
    unattended: int
    center: int
    with_driver: int
    gps: Decimal
    difference: Decimal
    difference_percent: Decimal | None


class KmDriver(BaseModel):
    driver: dict | None
    days: int
    on_duty: int
    off_duty: int
    gps: Decimal
    km_per_day: Decimal | None


class PendingReading(BaseModel):
    id: str
    vehicle: dict | None
    driver: dict | None
    kind: str
    value_km: int
    flags: list[str]
    recorded_at: datetime


class KilometersReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    max_days: int
    totals: dict
    by_vehicle: list[KmVehicle]
    by_driver: list[KmDriver]
    pending: list[PendingReading]
    pending_count: int


class AgingLine(BaseModel):
    driver: dict | None
    posted: Decimal
    pending: Decimal
    d0_1: Decimal
    d2_3: Decimal
    d4_7: Decimal
    d8_plus: Decimal
    oldest: date | None
    oldest_days: int | None


class CollectorLine(BaseModel):
    user: str
    receipts: int
    amount: Decimal
    confirmed: int
    reversed: int


class TreasuryLine(BaseModel):
    branch: dict | None
    opening: Decimal
    received: Decimal
    paid_out: Decimal
    closing: Decimal


class DepositLine(BaseModel):
    id: str
    business_date: date
    branch: dict | None
    amount: Decimal
    reference: str | None
    by: str
    reversed: bool
    has_receipt: bool = False


class CashReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    as_of: date
    aging: dict
    collectors: list[CollectorLine]
    treasury: list[TreasuryLine] | None
    deposits: list[DepositLine] | None


class PayrollRunLine(BaseModel):
    id: str
    month: date
    company: dict
    status: str
    lines: int
    gross: Decimal
    deductions: Decimal
    net: Decimal
    installments_due: Decimal
    installments_deducted: Decimal
    carried: Decimal
    by_source: dict[str, dict[str, Decimal]]


class CarriedLine(BaseModel):
    run_id: str
    month: date
    employee: dict | None
    source_type: str
    reason: str
    due: Decimal
    deducted: Decimal
    carried: Decimal


class PayrollReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    runs: list[PayrollRunLine]
    totals: dict
    carried: list[CarriedLine]


class FleetVehicle(BaseModel):
    vehicle: dict
    status: str
    driver: PersonRef | None
    days_held: int
    use_percent: Decimal | None


class FleetReport(BaseModel):
    """FR-RPT-01: statuses, vehicles with no driver, daily use."""

    from_: date = Field(alias="from")
    to: date
    statuses: dict[str, int]
    without_driver: int
    use_percent: Decimal | None
    by_vehicle: list[FleetVehicle]
    by_day: list[dict]

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
