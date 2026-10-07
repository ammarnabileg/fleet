import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Source = Literal["attendance", "cash", "orders", "complaints", "accidents", "tracking"]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,39}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
Amount = Annotated[Decimal, Field(ge=0, le=1000, max_digits=10, decimal_places=3)]


class Name(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ar: Text
    en: Text


class TypeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code | None = None  # on creating
    name: Name
    source: Source | None = None  # on creating
    amount: Amount | None = None
    active: bool = True
    version: int | None = None


class TypeOut(BaseModel):
    id: int
    code: str
    name: dict
    source: str
    amount: Decimal | None
    active: bool
    version: int


class CauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code | None = None
    name: Name
    active: bool = True
    version: int | None = None


class CauseOut(BaseModel):
    id: int
    code: str
    name: dict
    active: bool
    version: int


class ViolationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: uuid.UUID
    type_id: int
    occurred_at: AwareDatetime
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
    reference: Text | None = None
    cause_id: int | None = None
    evidence_sha256: Sha | None = None
    alert_id: uuid.UUID | None = None


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Amount | None = None  # none: the type's; zero: a warning
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Reason


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uphold: bool
    note: Reason


class ObjectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Reason
    file_sha256: Sha | None = None


class ViolationOut(BaseModel):
    id: str
    number: int
    company_id: int
    driver: dict | None
    type: dict
    cause: dict | None
    vehicle_plate: str | None
    occurred_at: datetime
    business_date: date
    description: str
    reference: str | None
    evidence_sha256: str | None
    origin: str
    status: str
    final: bool
    amount: Decimal | None
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    objection_deadline: datetime | None
    objection: str | None
    objection_sha256: str | None
    objected_at: datetime | None
    final_note: str | None
    final_by: str | None
    final_at: datetime | None
    deduction: dict | None
    created_by: str | None
    created_at: datetime
    version: int


class DriverViolationOut(BaseModel):
    id: str
    number: int
    type_name: dict
    occurred_at: datetime
    description: str | None
    reference: str | None
    amount: Decimal | None
    status: str
    objection_deadline: datetime | None
    can_object: bool
    objection: str | None
    final_note: str | None
