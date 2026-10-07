from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Amount = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_date: date
    orders_count: int | None = Field(None, ge=0, le=500)
    cash_amount: Amount | None = None
    valid_day: bool | None = None  # when the driver's platform asks: did the platform count the day
    screenshot_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    notes: str | None = Field(None, max_length=500)


class ReportFormOut(BaseModel):
    fields: list[str]  # orders, cash, valid_day: what this driver's platform asks for
    screenshot: bool


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class ReportOut(BaseModel):
    id: str
    late: bool  # sent after its own day
    driver: PersonRef | None
    company_id: int
    vehicle_plate: str | None
    business_date: date
    orders_count: int | None
    cash_amount: Decimal
    approved_cash: Decimal | None
    valid_day: bool | None
    has_screenshot: bool
    notes: str | None
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None
    review_note: str | None


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cash_amount: Amount | None = None  # the counted cash when it differs from the report
    reason: Reason | None = None


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason
