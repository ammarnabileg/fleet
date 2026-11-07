import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
LeaveKind = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
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
    paid: bool = False  # an emergency or other leave the office makes paid (with approve)
    override: bool = False  # registered although a rule says no (audited)
    followup_from: date | None = None  # the follow-up alert counts from this day (today by default)


class PreviewIn(_In):
    employee_id: uuid.UUID
    kind: LeaveKind
    date_from: date
    date_to: date
    paid: bool = False


class DriverPreviewIn(_In):
    kind: LeaveKind
    date_from: date
    date_to: date


class DriverLeaveIn(DriverPreviewIn):
    client_ref: uuid.UUID
    reason: Note | None = None
    file_sha256: Sha | None = None
    followup_from: date | None = None


class FollowupIn(_In):
    followup_from: date


class FollowedUpIn(_In):
    note: Short | None = None


class Tier(_In):
    days: int | None = Field(None, ge=1, le=400)  # None: no end (the last tier only)
    pay_percent: int = Field(ge=0, le=100)


class LeaveTypeIn(_In):
    version: int
    name: dict[str, Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]] | None = None
    legal_ref: Short | None = None
    tiers: Annotated[list[Tier], Field(min_length=1, max_length=10)] | None = None
    tier_period: Literal["occurrence", "service_year"] | None = None
    max_per_occurrence: int | None = Field(None, ge=1, le=400)
    max_per_year: int | None = Field(None, ge=1, le=400)
    max_per_service: int | None = Field(None, ge=1, le=2000)
    min_service_months: int | None = Field(None, ge=0, le=600)
    once_per_service: bool | None = None
    requires_attachment: bool | None = None
    eligible_gender: Literal["male", "female"] | None = None
    counts: Literal["calendar", "working"] | None = None
    accrues: bool | None = None
    office_may_pay: bool | None = None
    driver_may_request: bool | None = None
    active: bool | None = None
    sort_order: int | None = Field(None, ge=0, le=1000)


# fields a null clears (the others: null leaves them as they are)
NULLABLE_TYPE_FIELDS = ("legal_ref", "max_per_occurrence", "max_per_year", "max_per_service", "eligible_gender")


class LeaveTypeOut(BaseModel):
    code: str
    name: dict
    legal_ref: str | None
    tiers: list[dict]
    tier_period: str
    max_per_occurrence: int | None
    max_per_year: int | None
    max_per_service: int | None
    min_service_months: int
    once_per_service: bool
    requires_attachment: bool
    eligible_gender: str | None
    counts: str
    accrues: bool
    office_may_pay: bool
    driver_may_request: bool
    active: bool
    sort_order: int
    version: int
    updated_at: datetime


class Problem(BaseModel):
    code: str
    params: dict


class PreviewOut(BaseModel):
    kind: str
    date_from: date
    date_to: date
    calendar_days: int
    days: int
    split: list[dict]
    paid_days: int
    unpaid_days: int
    pay_days: str
    tier_days_before: int
    balance: dict | None
    problems: list[Problem]
    warnings: list[str]


class BalanceOut(BaseModel):
    code: str
    name: dict
    eligible: bool
    reason: str | None
    requires_attachment: bool
    tiers: list[dict]
    counts: str
    max_per_occurrence: int | None
    used_year: int
    used_service: int
    pending: int
    service_year: dict
    left_year: int | None
    left_service: int | None
    accrued: int | None
    available: int | None


class DriverLeaveOut(BaseModel):
    id: str
    kind: str
    kind_name: dict
    date_from: date
    date_to: date
    days: int
    split: list[dict]
    status: str
    reason: str | None
    decision_note: str | None
    cancel_reason: str | None
    followup_from: date
    has_file: bool
    created_at: datetime


class DriverLeavesOut(BaseModel):
    types: list[BalanceOut]
    requests: list[DriverLeaveOut]


class ApproveIn(_In):
    note: Short | None = None
    paid: bool = False  # an emergency or other leave made paid


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
    kind_name: dict | None
    date_from: date
    date_to: date
    days: int
    counted_days: int
    split: list[dict]
    unpaid_days: int
    paid_override: bool
    rules_overridden: bool
    source: str
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
    followup_from: date
    followup_due: date
    followed_up_at: datetime | None
    followed_up_by: str | None
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
