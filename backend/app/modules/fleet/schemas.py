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
    started_at: datetime
    last_odometer_km: int | None


class DriverTodayOut(BaseModel):
    custody: DriverCustody | None
    start_day_done: bool
