import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Plate = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Km = Annotated[int, Field(ge=0, le=5_000_000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
ManualStatus = Literal["available", "maintenance", "accident", "inactive"]


class VehicleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_number: Plate
    make: Short | None = None
    model: Short | None = None
    year: int | None = Field(None, ge=1980, le=2100)
    color: Short | None = None
    vin: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=5, max_length=30)] | None = (
        None
    )
    company_id: int
    branch_id: int | None = None
    status: ManualStatus = "available"
    last_odometer_km: Km | None = None  # the reading when the vehicle joins the fleet


class VehicleUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    plate_number: Plate | None = None
    make: Short | None = None
    model: Short | None = None
    year: int | None = Field(None, ge=1980, le=2100)
    color: Short | None = None
    vin: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=5, max_length=30)] | None = (
        None
    )
    company_id: int | None = None
    branch_id: int | None = None
    status: ManualStatus | None = None


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class VehicleCustody(BaseModel):
    id: str
    driver: PersonRef | None
    started_at: datetime
    kind: str


class VehicleOut(BaseModel):
    id: str
    plate_number: str
    make: str | None
    model: str | None
    year: int | None
    color: str | None
    vin: str | None
    company_id: int
    branch_id: int
    status: str
    last_odometer_km: int | None
    custody: VehicleCustody | None
    version: int


class PhotoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Literal["front", "back", "left", "right", "interior", "other"]
    sha256: Sha256


class HandoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: str
    driver_id: str
    odometer_km: Km
    photo_sha256: Sha256
    started_at: AwareDatetime | None = None  # now when omitted; may be up to 7 days in the past
    kind: Literal["normal", "emergency"] = "normal"
    reason: Reason | None = None
    photos: list[PhotoIn] = Field(default_factory=list, max_length=12)  # vehicle condition


class ReturnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    odometer_km: Km
    photo_sha256: Sha256
    ended_at: AwareDatetime | None = None
    photos: list[PhotoIn] = Field(default_factory=list, max_length=12)


class CustodyVehicle(BaseModel):
    id: str | None
    plate_number: str | None


class ReadingOut(BaseModel):
    id: str
    vehicle_plate: str | None
    driver: PersonRef | None
    kind: str
    value_km: int
    corrected_km: int | None
    effective_km: int
    recorded_at: datetime
    business_date: date
    lat: float | None
    lng: float | None
    flags: list[str]
    review_status: str
    review_reason: str | None
    reviewed_at: datetime | None
    source: str


class CustodyOut(BaseModel):
    id: str
    vehicle: CustodyVehicle
    driver: PersonRef | None
    company_id: int
    started_at: datetime
    ended_at: datetime | None
    kind: str
    reason: str | None
    needs_review: bool


class CustodyPhotoOut(BaseModel):
    stage: str
    position: str
    sha256: str


class CustodyDetailOut(CustodyOut):
    readings: list[ReadingOut]
    photos: list[CustodyPhotoOut]


class CustodyReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Reason


class ReadingReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrected_km: Km | None = None  # null: the reading is accepted as it is
    reason: Reason


class DriverReadingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["start_day", "end_day"] = "start_day"
    value_km: Km
    photo_sha256: Sha256
    recorded_at: AwareDatetime
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)


class DriverCustody(BaseModel):
    id: str
    plate_number: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    started_at: datetime
    last_odometer_km: int | None
    in_maintenance: bool = False  # at a center: still his, no day starts with it until he collects it
    maintenance_center: str | None = None  # the center it is at


class DriverTodayOut(BaseModel):
    custody: DriverCustody | None
    start_day_done: bool
    end_day_done: bool  # the day closed: end-of-day reading, or the vehicle returned
    sessions: int = 0  # today's work sessions: after ending the day he may start again, and its report adds up
    recent: dict[str, int] = {}  # the two days before: their sessions, for a report sent late
    day_started_at: datetime | None = None  # the session he is in (or ended last): its start of day
    day_start_km: int | None = None


class VehicleChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_plate: Plate  # the other car, as he reads it on its plate; it must be one of his company's vehicles
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class RequestedVehicle(BaseModel):
    """The car he asked for, as it is now: free, or in someone's custody. found is false only for a request made
    before the plate was asked (or a vehicle since removed)."""

    found: bool
    plate: str
    id: str | None = None
    status: str | None = None
    holder: dict | None = None  # {id, name}: the driver holding it now, if anyone


class VehicleChangeOut(BaseModel):
    id: str
    status: str  # pending | done | rejected
    reason: str
    note: str | None
    created_at: datetime
    decided_at: datetime | None
    requested_plate: str = ""  # '' for a request made before the plate was asked
    vehicle_plate: str | None = None
    vehicle_id: str | None = None
    driver: dict | None = None
    requested_vehicle: RequestedVehicle | None = None  # the office's list only
    decided_by: str | None = None  # the office's list only: the user who closed it (or who took the car back)


class MyVehicle(BaseModel):
    plate_number: str
    make: str | None
    model: str | None
    year: int | None
    color: str | None
    since: datetime
    last_odometer_km: int | None
    last_reading_at: datetime | None
    registration_expiry: date | None


class ClaimPhotoOut(BaseModel):
    position: str
    sha256: str


class VehicleClaimOut(BaseModel):
    id: str
    status: str  # pending | approved | rejected | superseded (he got another car meanwhile)
    plate: str
    vehicle_id: str | None = None
    odometer_km: int
    claimed_at: datetime
    created_at: datetime
    note: str | None
    decided_at: datetime | None
    photos: list[ClaimPhotoOut] = []
    driver: dict | None = None  # the office's list only
    vehicle_last_km: int | None = None  # the office's list only: the car's last reading, to compare
    vehicle_status: str | None = None  # the office's list only: the car as it is now
    holder: dict | None = None  # the office's list only: who holds the car now, if anyone
    decided_by: str | None = None  # the office's list only
    custody_id: str | None = None  # approved: the custody it became
    expired: bool = False  # waiting beyond the backdate limit: it can only be refused


class MyVehicleOut(BaseModel):
    vehicle: MyVehicle | None
    change_request: VehicleChangeOut | None
    claim: VehicleClaimOut | None = None  # no car: the car he registered, waiting or refused


class CloseChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)] | None = None


class TransferIn(BaseModel):
    """The car X handed to driver A while X is held by B, or while A holds Y, in one step. release: B leaves X (and A
    gives Y back); swap: B takes Y and A takes X. other_*: Y's reading and photos, needed when A holds Y."""

    model_config = ConfigDict(extra="forbid")

    vehicle_id: str
    driver_id: str
    mode: Literal["release", "swap"]
    odometer_km: Km
    photo_sha256: Sha256
    photos: list[PhotoIn] = Field(default_factory=list, max_length=12)
    started_at: AwareDatetime | None = None
    other_odometer_km: Km | None = None
    other_photo_sha256: Sha256 | None = None
    other_photos: list[PhotoIn] = Field(default_factory=list, max_length=12)
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None


class TransferOut(BaseModel):
    mode: str
    started: list[CustodyOut]
    ended: list[CustodyOut]


class TransferHolder(BaseModel):
    driver: PersonRef | None
    custody_id: str
    since: datetime


class TransferDriverVehicle(BaseModel):
    id: str
    plate_number: str
    custody_id: str
    since: datetime
    last_odometer_km: int | None


class TransferCheckOut(BaseModel):
    holder: TransferHolder | None  # who holds the car now
    driver_vehicle: TransferDriverVehicle | None  # the car the driver holds now
    modes_allowed: list[str]  # handover (nobody busy) | release | swap; empty: he already holds this car


class DriverClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate: Plate  # as he reads it on the car; one of his company's vehicles
    odometer_km: Km
    photo_sha256: Sha256  # the odometer, from the app's camera
    recorded_at: AwareDatetime  # the photo's time: the custody starts then once approved
    photos: list[PhotoIn | Sha256] = Field(default_factory=list, max_length=12)  # condition photos
    client_ref: uuid.UUID  # the app's id: a resend is answered vehicle_claim_exists


class ClaimDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)] | None = None
