import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class UserRef(BaseModel):
    id: str
    name: str


class AlertOut(BaseModel):
    id: str
    kind: str
    severity: str
    message: str  # what happened, as it stood when the alert was raised (or last refreshed: updated_at)
    params: dict
    company_id: int | None
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    updated_at: datetime | None
    status: str  # new (nobody has seen it), seen (acknowledged, still open), resolved
    acknowledged_at: datetime | None
    acknowledged_by: UserRef | None
    resolved_at: datetime | None
    resolved_by: UserRef | None
    resolution: str | None  # auto: its cause went away; manual: someone handled it
    resolution_note: str | None
    assigned_to: UserRef | None
    assigned_at: datetime | None
    escalated_at: datetime | None
    escalated_by: UserRef | None


class AlertEventOut(BaseModel):
    action: str
    at: datetime
    by: UserRef | None
    user: UserRef | None  # assigned or escalated to
    note: str | None


class AlertDetail(AlertOut):
    events: list[AlertEventOut]


class AlertSummary(BaseModel):
    open: int  # not handled yet
    critical: int
    warning: int
    info: int
    new: int  # open and seen by nobody: the bell
    mine: int  # open and assigned to the user asking
    latest: AlertOut | None  # the newest open alert


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Note  # what was done


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID | None  # none: nobody
    note: str | None = Field(default=None, max_length=500)


class EscalateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    note: Note  # why


class DriverNoticeOut(BaseModel):
    id: str
    kind: str
    message: str
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    read: bool


class DriverNoticesOut(BaseModel):
    unread: int
    items: list[DriverNoticeOut]


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)  # none: every notice


class ReadOut(BaseModel):
    count: int
