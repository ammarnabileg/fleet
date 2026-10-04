from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class Installment(BaseModel):
    month: date
    amount: Decimal


class DeductionOut(BaseModel):
    id: str
    employee: dict | None
    company_id: int
    source_type: str
    reason: str
    total: Decimal
    installments: int
    start_month: date
    schedule: list[Installment]
    status: str
    created_at: datetime
    created_by: str | None
    cancelled_at: datetime | None
    cancelled_by: str | None
    cancel_reason: str | None
