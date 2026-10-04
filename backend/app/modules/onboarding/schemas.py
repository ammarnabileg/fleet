from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
CivilId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{12}$")]
Position = Literal["front", "back", "left", "right", "interior", "other"]


class DocumentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_code: Code
    number: Short | None = None
    expiry_date: date | None = None
    front_sha256: Sha256 | None = None
    back_sha256: Sha256 | None = None


class PhotoEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Position
    sha256: Sha256


class VehicleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)] | None = None
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    odometer_photo: Sha256 | None = None
    photos: list[PhotoEntry] = Field(default_factory=list, max_length=12)


class Draft(BaseModel):
    """What the driver has entered so far. Saving a draft accepts gaps; submitting checks completeness."""

    model_config = ConfigDict(extra="forbid")

    civil_id: CivilId | None = None
    nationality: Short | None = None
    documents: list[DocumentEntry] = Field(default_factory=list, max_length=10)
    vehicle: VehicleEntry | None = None
    no_vehicle: bool = False  # the driver does not hold a vehicle yet


class DocumentTypeOut(BaseModel):
    code: str
    name: dict[str, str]
    requires_expiry: bool


class DriverView(BaseModel):
    required: bool  # the app shows the registration screens
    status: str  # none / draft / submitted / approved / rejected
    data: dict
    review_note: str | None
    required_documents: list[str]
    vehicle_photos: list[str]
    document_types: list[DocumentTypeOut]


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class SubmissionOut(BaseModel):
    id: str
    employee: PersonRef
    company_id: int
    status: str
    plate_number: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    review_note: str | None


class VehicleMatch(BaseModel):
    found: bool
    id: str | None
    status: str | None
    held_by_other: bool


class SubmissionDetail(SubmissionOut):
    phone: str | None
    data: dict
    vehicle: VehicleMatch | None


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
