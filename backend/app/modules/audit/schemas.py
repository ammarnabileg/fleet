from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_type: str
    actor_user_id: int | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: str | None
    company_id: int | None
    before: Any
    after: Any
    ip: str | None
    request_id: str | None
    device: str | None = None  # the browser, or the driver app and phone (FR-AUD-01)
    comment: str | None = None  # the reason or note given with the action


class AuditUserOut(BaseModel):
    id: str
    name: str
