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


class SummaryOut(BaseModel):
    from_: date = Field(alias="from")
    to: date
    rows: list[SummaryRow]
    totals: dict

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
