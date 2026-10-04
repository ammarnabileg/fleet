from datetime import datetime

from pydantic import BaseModel


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
