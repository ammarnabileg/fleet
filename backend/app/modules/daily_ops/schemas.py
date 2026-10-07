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
    end_reading: bool  # today's report, after a started day, needs the end-of-day reading first


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class ReportOut(BaseModel):
    id: str
    late: bool  # sent after its own day
    deviations: list[str]  # orders, cash: far from the driver's average (reviewers' list only)
    change_pending: bool  # a change asked for after approval waits for a decision
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


class ReadingBrief(BaseModel):
    id: str
    kind: str  # start_day | end_day | return
    km: int
    recorded_at: datetime
    flags: list[str]


class Average(BaseModel):
    days: int  # approved reports in the 30 days before
    orders: Decimal | None
    cash: Decimal | None
    km: int | None
    km_days: int


class EvidenceOut(BaseModel):
    start: ReadingBrief | None
    end: ReadingBrief | None
    km: int | None
    average: Average
    deviations: list[str]


class ReportEditIn(BaseModel):
    """Only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    orders_count: int | None = Field(None, ge=0, le=500)
    cash_amount: Amount | None = None
    valid_day: bool | None = None
    screenshot_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    notes: str | None = Field(None, max_length=500)


class ChangeRequestIn(ReportEditIn):
    reason: Reason


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Reason | None = None  # required to refuse


class ChangeOut(BaseModel):
    id: str
    report_id: str
    driver: PersonRef | None
    business_date: date
    kind: str  # edit | returned | request
    status: str  # applied | pending | approved | rejected
    before: dict
    after: dict
    reason: str | None
    by_driver: bool
    created_at: datetime
    decided_at: datetime | None
    decision_note: str | None
