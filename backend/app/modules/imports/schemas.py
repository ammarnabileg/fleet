from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Counts(BaseModel):
    created: int
    updated: int


class IssueOut(BaseModel):
    sheet: str
    row: int  # the row number in Excel
    code: str  # message: translations "errors.<code>" (warnings too), filled with params
    params: dict


class ImportResult(BaseModel):
    applied: bool
    vehicles: Counts
    people: Counts
    documents: int
    opening_balances: int
    claims: int = 0  # drivers without a phone who may now sign in once with their civil ID
    errors: list[IssueOut]
    warnings: list[IssueOut]


class SheetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    kind: Literal["vehicles", "employees"]
    first_row: int = Field(ge=1, le=100_000)  # the first data row in Excel (rows above it are skipped)
    columns: dict[str, int]  # field -> column (0-based), as suggested by the preview and corrected by the user


class MappedPlan(BaseModel):
    """How to read a client's own workbook: which sheets, as what, from which columns, into which company."""

    model_config = ConfigDict(extra="forbid")

    company_id: int
    branch_id: int | None = None  # the main branch when left out
    # an employee is a driver when his profession contains one of these words
    driver_keywords: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]] = (
        Field(default_factory=lambda: ["سائق", "driver"], max_length=10)
    )
    sheets: list[SheetPlan] = Field(min_length=1, max_length=20)
    # drivers without a phone may sign in once with their civil ID and this password (then register their phone)
    claim_password: Annotated[str, StringConstraints(min_length=8, max_length=64)] | None = None
    claim_days: int = Field(14, ge=1, le=60)


class ColumnOut(BaseModel):
    index: int
    header: str
    samples: list[str]


class SheetOut(BaseModel):
    name: str
    rows: int
    header_row: int | None
    first_row: int
    columns: list[ColumnOut]
    kind: str | None
    mapping: dict[str, int]


class FieldOut(BaseModel):
    key: str
    required: bool


class PreviewOut(BaseModel):
    sheets: list[SheetOut]
    fields: dict[str, list[FieldOut]]
