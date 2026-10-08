import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Kind = Literal["periodic", "mechanical", "electrical", "tyres", "battery", "ac", "bodywork", "other"]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- centers and their portal accounts


class CenterIn(_In):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
    specialty: Short | None = None
    contact_name: Short | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    is_active: bool = True


class CenterUpdateIn(CenterIn):
    version: int
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)] | None = None
    is_active: bool | None = None


class CenterOut(BaseModel):
    id: str
    name: str
    specialty: str | None
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    is_active: bool
    version: int
    users: int
    at_center: int


class PortalUserIn(_In):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=60)]
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class PortalUserActiveIn(_In):
    is_active: bool


class PortalUserOut(BaseModel):
    id: str
    username: str
    full_name: str
    phone: str | None
    is_active: bool
    last_login_at: datetime | None


# ---- requests


class RequestIn(_In):
    """From the office: any vehicle in scope; an emergency is approved at once and reviewed afterwards."""

    vehicle_id: uuid.UUID
    kind: Kind
    description: Text
    odometer_km: Annotated[int, Field(ge=0, le=5_000_000)] | None = None
    emergency: bool = False
    photos: list[Sha] = Field(default_factory=list, max_length=10)


class DriverRequestIn(_In):
    """From the driver app, for the vehicle the driver holds. client_ref: the app's id, so a retry is recognised.
    center_id: the center he takes the car to, when requests go straight to the center (the settings)."""

    client_ref: uuid.UUID
    kind: Kind
    description: Text
    odometer_km: Annotated[int, Field(ge=0, le=5_000_000)] | None = None
    photos: list[Sha] = Field(default_factory=list, max_length=10)
    center_id: uuid.UUID | None = None


class DriverCenterOut(BaseModel):
    id: str
    name: str
    specialty: str | None
    phone: str | None
    address: str | None


class DriverFormOut(BaseModel):
    direct_to_center: bool  # he picks the center and the request goes straight to it
    centers: list[DriverCenterOut]


class DriverPickupIn(_In):
    """The driver collected the car from the center: its odometer, photographed with this phone's camera."""

    odometer_km: Annotated[int, Field(ge=0, le=5_000_000)]
    odometer_photo: Sha
    picked_up_at: AwareDatetime | None = None  # when the photo was taken (sent later from the queue)


class NoteIn(_In):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ReasonIn(_In):
    reason: Reason


class ReferIn(_In):
    center_id: uuid.UUID
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ReceiveIn(_In):
    """The center's reception: when the vehicle arrived, its odometer with a photo, its condition."""

    received_at: AwareDatetime | None = None  # now when omitted; up to 7 days in the past
    odometer_km: Annotated[int, Field(ge=0, le=5_000_000)]
    odometer_photo: Sha
    condition_note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    photos: list[Sha] = Field(default_factory=list, max_length=12)


class StatusIn(_In):
    status: Literal["inspection", "in_repair", "waiting_parts"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ItemIn(_In):
    kind: Literal["part", "labour", "other"]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    quantity: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)] = Decimal(1)
    unit_price: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class QuoteIn(_In):
    amount: Amount
    items: list[ItemIn] = Field(default_factory=list, max_length=100)
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    file_sha256: Sha | None = None


class CompleteIn(_In):
    repair_details: Text
    final_odometer_km: Annotated[int, Field(ge=0, le=5_000_000)]
    final_odometer_photo: Sha
    photos: list[Sha] = Field(default_factory=list, max_length=12)


class InvoiceIn(_In):
    """Number, total and file are checked by the service, so a missing one is named in the error (UAT-22)."""

    request_id: uuid.UUID | None = None
    number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    invoice_date: date | None = None
    total: Annotated[Decimal, Field(max_digits=12, decimal_places=3)] | None = None
    file_sha256: Sha | None = None
    items: list[ItemIn] = Field(default_factory=list, max_length=200)
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class OfficeInvoiceIn(InvoiceIn):
    """Entered by the accountant: any center; the company comes from the request, or is given."""

    center_id: uuid.UUID
    company_id: int | None = None


class PaidIn(_In):
    payment_ref: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None


class Item(BaseModel):
    kind: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class QuoteOut(BaseModel):
    id: str
    amount: Decimal
    items: list[Item]
    notes: str | None
    has_file: bool
    file_sha256: str | None
    status: str
    auto_approved: bool
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    reason: str | None


class InvoiceOut(BaseModel):
    id: str
    center: dict
    request: dict | None
    vehicle_plate: str | None
    company_id: int
    number: str
    invoice_date: date
    total: Decimal
    items: list[Item]
    notes: str | None
    file_sha256: str
    flags: list[str]
    quote_amount: Decimal | None
    status: str
    payment_status: str
    paid_at: datetime | None
    payment_ref: str | None
    created_at: datetime
    created_by: str | None
    decided_at: datetime | None
    decided_by: str | None
    reason: str | None
    version: int


class EventOut(BaseModel):
    status: str
    at: datetime
    by: str | None
    note: str | None


class DurationOut(BaseModel):
    status: str
    started_at: datetime
    ended_at: datetime | None
    seconds: int


class PhotoOut(BaseModel):
    stage: str
    sha256: str


class RequestOut(BaseModel):
    id: str
    number: int
    vehicle: dict
    company_id: int
    driver: dict | None
    kind: str
    description: str
    odometer_km: int | None
    emergency: bool
    emergency_reviewed: bool
    status: str
    source: str
    center: dict | None
    created_at: datetime
    referred_at: datetime | None
    received_at: datetime | None
    received_km: int | None
    ready_at: datetime | None
    picked_up_at: datetime | None
    closed_at: datetime | None
    stay_seconds: int | None
    decision_note: str | None
    cancel_reason: str | None
    is_new: bool
    version: int


class RequestDetailOut(RequestOut):
    condition_note: str | None
    repair_details: str | None
    final_km: int | None
    completed_at: datetime | None
    photos: list[PhotoOut]
    events: list[EventOut]
    durations: list[DurationOut]
    quotes: list[QuoteOut]
    invoices: list[InvoiceOut]


class DriverRequestOut(BaseModel):
    id: str
    number: int
    vehicle_plate: str
    kind: str
    description: str
    status: str
    center: dict | None
    created_at: datetime
    ready_at: datetime | None
    picked_up_at: datetime | None
    decision_note: str | None
