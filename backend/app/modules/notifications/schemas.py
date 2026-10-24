import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

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
    title: str | None = None  # a broadcast's title and body, apart (the message holds both)
    body: str | None = None


class DriverNoticesOut(BaseModel):
    unread: int
    items: list[DriverNoticeOut]


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)  # none: every notice


class ReadOut(BaseModel):
    count: int


# ------------------------------------------------------------------ broadcasts (ركن الإشعارات)

BroadcastLang = Literal["ar", "en", "fr", "sw", "hi", "fil"]


class AudienceIn(BaseModel):
    kind: Literal["all", "company", "platform", "on_duty", "selected"]
    company_ids: list[int] = Field(default_factory=list, max_length=200)
    platform_ids: list[int] = Field(default_factory=list, max_length=200)
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5000)


class BroadcastPreviewIn(BaseModel):
    audience: AudienceIn
    channels: list[Annotated[str, StringConstraints(max_length=31)]] = Field(default_factory=list, max_length=10)


class BroadcastIn(BroadcastPreviewIn):
    title: dict[BroadcastLang, Annotated[str, StringConstraints(max_length=120)]]
    body: dict[BroadcastLang, Annotated[str, StringConstraints(max_length=2000)]]
    scheduled_at: AwareDatetime | None = None
    send: bool = True


class ResendIn(BaseModel):
    channel: Annotated[str, StringConstraints(max_length=31)] | None = None


class BroadcastOut(BaseModel):
    id: str
    title: dict[str, str]
    body: dict[str, str]
    audience: dict
    channels: list[str]
    status: str
    scheduled_at: datetime | None
    recipients: int
    created_at: datetime
    started_at: datetime | None
    sent_at: datetime | None
    cancelled_at: datetime | None
    stats: dict[str, dict[str, int]]
    requeued: int | None = None


class BroadcastDeliveryOut(BaseModel):
    driver: dict | None
    channel: str
    status: str
    reason: str | None
    lang: str | None
    attempts: int
    updated_at: datetime
    sent_at: datetime | None
