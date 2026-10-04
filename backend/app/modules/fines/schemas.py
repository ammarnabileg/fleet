import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.payroll.schemas import DeductionOut

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FineIn(_In):
    vehicle_id: uuid.UUID
    occurred_at: AwareDatetime  # the time on the ticket: it decides who was driving
    violation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)]
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
    reference_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] | None = None
    location_text: Short | None = None
    file_sha256: Sha | None = None
    notes: Note | None = None


class ChargeIn(_In):
    installments: Annotated[int, Field(ge=1, le=60)]
    start_month: date | None = None  # any day of the month; next month when omitted
    reason: Short | None = None  # on the payslip; "Fine #N" when omitted


class ReasonIn(_In):
    reason: Reason


class PaidIn(_In):
    payment_ref: Short | None = None


class FineOut(BaseModel):
    id: str
    number: int
    vehicle: dict
    company_id: int
    driver: dict | None
    occurred_at: datetime
    reference_no: str | None
    violation: str
    location_text: str | None
    amount: Decimal
    has_file: bool
    file_sha256: str | None
    notes: str | None
    status: str
    can_decide: bool
    decided_at: datetime | None
    decided_by: str | None
    decision_note: str | None
    deduction: DeductionOut | None
    paid_at: datetime | None
    paid_by: str | None
    payment_ref: str | None
    created_at: datetime
    created_by: str | None
    cancel_reason: str | None
    version: int


class DriverFineOut(BaseModel):
    id: str
    number: int
    vehicle_plate: str
    occurred_at: datetime
    violation: str
    location_text: str | None
    amount: Decimal
    status: str
    deduction: DeductionOut | None
