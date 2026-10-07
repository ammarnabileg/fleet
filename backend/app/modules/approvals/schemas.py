import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import LocalizedText

Process = Literal[
    "daily_report",
    "maintenance_request",
    "maintenance_quote",
    "maintenance_invoice",
    "accident_estimate",
    "expense",
    "payroll_run",
]
RoleCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepIn(_In):
    name: LocalizedText
    role: RoleCode | None = None
    user_id: uuid.UUID | None = None
    min_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)] = Decimal(0)
    escalate_after_hours: Annotated[int, Field(gt=0, le=24 * 30)] | None = None
    escalate_role: RoleCode | None = None


class WorkflowIn(_In):
    version: int
    active: bool
    steps: Annotated[list[StepIn], Field(max_length=10)]


class Ref(BaseModel):
    id: str
    name: str


class RoleRef(BaseModel):
    code: str
    name: dict


class StepOut(BaseModel):
    position: int
    name: dict
    role: RoleRef | None
    user: Ref | None
    holders: int
    min_amount: Decimal
    escalate_after_hours: int | None
    escalate_role: RoleRef | None


class WorkflowOut(BaseModel):
    process: Process
    active: bool
    version: int
    updated_at: datetime | None
    pending: int
    steps: list[StepOut]


class OptionsOut(BaseModel):
    roles: list[RoleRef]
    users: list[Ref]


class RequestStepOut(BaseModel):
    name: dict
    role: RoleRef | None
    user: Ref | None
    escalate_role: RoleRef | None


class DecisionOut(BaseModel):
    step: int
    decision: Literal["approved", "rejected", "escalated"]
    by: Ref | None
    on_behalf_of: Ref | None
    reason: str | None
    at: datetime


class RequestOut(BaseModel):
    id: str
    process: Process
    document_id: str
    document_ref: str
    company_id: int | None
    amount: Decimal
    status: Literal["pending", "approved", "rejected", "cancelled"]
    current: int
    escalated: bool
    step_since: datetime
    created_at: datetime
    closed_at: datetime | None
    cancel_note: str | None
    steps: list[RequestStepOut]
    decisions: list[DecisionOut]


class DecideIn(_In):
    approve: bool
    reason: Note | None = None


class DelegationIn(_In):
    delegate_id: uuid.UUID
    date_from: date
    date_to: date
    reason: Note | None = None
    user_id: uuid.UUID | None = None  # someone else's, by whoever manages the workflows


class DelegationOut(BaseModel):
    id: str
    user: Ref
    delegate: Ref
    date_from: date
    date_to: date
    reason: str | None
    status: Literal["active", "upcoming", "ended", "cancelled"]
