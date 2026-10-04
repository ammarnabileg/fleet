from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_type: str
    actor_user_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    branch_id: int | None
    before: Any
    after: Any
    ip: str | None
    request_id: str | None
