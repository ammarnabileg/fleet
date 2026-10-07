import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertOut(BaseModel):
    id: str
    kind: str
    severity: str
    message: str
    params: dict
    company_id: int | None
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    acknowledged_at: datetime | None


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
