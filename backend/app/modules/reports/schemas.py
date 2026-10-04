from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Dashboard(BaseModel):
    """A section is absent when the user lacks its permission."""

    model_config = ConfigDict(extra="allow")

    as_of: datetime
    alerts: dict[str, int]
    vehicles: dict[str, int] | None = None
    drivers: dict | None = None
    daily_reports: dict | None = None
    cash: dict | None = None
    documents: dict[str, int] | None = None
    maintenance: dict[str, int] | None = None
    accidents: dict[str, int] | None = None


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class SummaryRow(BaseModel):
    driver: PersonRef
    employee_number: str
    company_id: int
    days: int
    orders: int
    reported_cash: Decimal
    approved_cash: Decimal
    waiting: int
    rejected: int


class SummaryOut(BaseModel):
    from_: date = Field(alias="from")
    to: date
    rows: list[SummaryRow]
    totals: dict

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
