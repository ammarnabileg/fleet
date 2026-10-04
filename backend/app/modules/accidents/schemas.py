import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.payroll.schemas import DeductionOut

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Report(_In):
    occurred_at: AwareDatetime | None = None  # now when omitted
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    location_text: Short | None = None
    description: Text
    injuries: bool = False
    injuries_note: Note | None = None
    other_party: Note | None = None  # the other vehicle, its driver, their insurer
    photos: list[Sha] = Field(default_factory=list, max_length=12)
    police_report: Sha | None = None  # may come later (BRD FR-ACC-02)
    police_report_no: Short | None = None


class AccidentIn(_Report):
    """Reported by the office (accidents.create)."""

    vehicle_id: uuid.UUID


class DriverAccidentIn(_Report):
    """From the app: the vehicle the driver held at that moment; photos from this phone's camera."""

    client_ref: uuid.UUID


class PhotosIn(_In):
    photos: list[Sha] = Field(min_length=1, max_length=12)


class PoliceReportIn(_In):
    file_sha256: Sha
    number: Short | None = None


class ReferIn(_In):
    center_id: uuid.UUID
    note: Note | None = None


class ReasonIn(_In):
    reason: Reason


class NoteIn(_In):
    note: Note | None = None


class ItemIn(_In):
    kind: Literal["part", "labour", "other"]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    quantity: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)] = Decimal(1)
    unit_price: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class EstimateIn(_In):
    """The center's estimate of the damage, item by item (BRD FR-ACC-04)."""

    total: Amount
    items: list[ItemIn] = Field(min_length=1, max_length=100)
    notes: Note | None = None
    file_sha256: Sha | None = None
    photos: list[Sha] = Field(default_factory=list, max_length=12)


class OutcomeIn(_In):
    """The liability per the police report (BRD FR-ACC-06) and, when the driver is liable, the deduction
    (FR-ACC-07): the approved damage in full or by the liability percentage, in monthly installments."""

    liability: Literal["none", "driver", "shared"]
    percent: Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)] | None = None
    note: Note | None = None
    installments: Annotated[int, Field(ge=1, le=60)] | None = None
    start_month: date | None = None  # any day of the month; the first month deducted
    reason: Short | None = None  # shown on the payslip; "Accident #N" when omitted


# ---- outputs


class Item(BaseModel):
    kind: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class EventOut(BaseModel):
    kind: str
    at: datetime
    by: str | None
    note: str | None


class RepairOut(BaseModel):
    id: str
    number: int
    status: str
    actual_cost: Decimal | None
    invoices_pending: int
    picked_up_at: datetime | None


class AccidentOut(BaseModel):
    id: str
    number: int
    vehicle: dict
    company_id: int
    driver: dict | None
    occurred_at: datetime
    location_text: str | None
    lat: float | None
    lng: float | None
    description: str
    injuries: bool
    source: str
    stage: str
    status: str
    has_police_report: bool
    center: dict | None
    estimate_status: str
    estimate_total: Decimal | None
    liability: str | None
    liability_percent: Decimal | None
    deduction_total: Decimal | None
    created_at: datetime
    version: int


class AccidentDetailOut(AccidentOut):
    injuries_note: str | None
    other_party: str | None
    police_report_sha256: str | None
    police_report_no: str | None
    police_report_at: datetime | None
    referred_at: datetime | None
    estimate_items: list[Item]
    estimate_notes: str | None
    estimate_file_sha256: str | None
    estimated_at: datetime | None
    estimate_decided_at: datetime | None
    estimate_decided_by: str | None
    estimate_reason: str | None
    outcome_note: str | None
    outcome_at: datetime | None
    outcome_by: str | None
    deduction: DeductionOut | None
    repair: RepairOut | None
    cost_difference: Decimal | None
    cancel_reason: str | None
    closed_at: datetime | None
    photos: list[str]
    events: list[EventOut]


class PortalAccidentOut(BaseModel):
    """What a center sees: the vehicle and the damage, not the driver, the other party or the liability."""

    id: str
    number: int
    vehicle: dict
    occurred_at: datetime
    description: str
    estimate_status: str
    estimate_total: Decimal | None
    estimate_items: list[Item]
    estimate_notes: str | None
    estimate_reason: str | None
    estimated_at: datetime | None
    referred_at: datetime | None
    is_new: bool
    photos: list[str]


class DriverAccidentOut(BaseModel):
    id: str
    number: int
    vehicle_plate: str
    occurred_at: datetime
    description: str
    stage: str
    has_police_report: bool
    liability: str | None
    liability_percent: Decimal | None
    deduction: DeductionOut | None
    created_at: datetime
