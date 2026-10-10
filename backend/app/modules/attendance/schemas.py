import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
LeaveKind = Literal["annual", "sick", "emergency", "unpaid", "other"]
MarkKind = Literal["absence", "leave", "rest", "no_vehicle", "system_fault"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LeaveIn(_In):
    employee_id: uuid.UUID
    kind: LeaveKind
    date_from: date
    date_to: date
    note: Note | None = None
    file_sha256: Sha | None = None
    approve: bool = False  # registered as approved (the leave was already agreed)


class ApproveIn(_In):
    note: Short | None = None


class RejectIn(_In):
    note: Reason


class CancelIn(_In):
    reason: Reason


class DayRef(_In):
    employee_id: uuid.UUID
    day: date


class MarkIn(_In):
    kind: MarkKind
    note: Short | None = None
    days: Annotated[list[DayRef], Field(min_length=1, max_length=1000)]


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class EmployeeRef(PersonRef):
    employee_number: str


class LeaveOut(BaseModel):
    id: str
    employee: PersonRef | None
    company_id: int
    kind: str
    date_from: date
    date_to: date
    days: int
    status: str
    note: str | None
    has_file: bool
    file_sha256: str | None
    created_by: str | None
    created_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    cancel_reason: str | None
    version: int


class DayOut(BaseModel):
    employee: EmployeeRef
    day: date
    held_vehicle: bool


class ToClassifyOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    total: int
    days: list[DayOut]


class MarkOut(BaseModel):
    employee: EmployeeRef
    day: date
    kind: str
    note: str | None
    marked_by: str | None
    marked_at: datetime


class MarkedOut(BaseModel):
    marked: int
