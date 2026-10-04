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
