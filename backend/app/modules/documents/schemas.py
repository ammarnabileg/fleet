from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

OwnerType = Literal["employee", "vehicle", "company"]


class DocumentTypeOut(BaseModel):
    code: str
    name: dict[str, str]
    applies_to: str
    requires_expiry: bool


class DocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_type: OwnerType
    owner_id: str  # public id of the employee / vehicle / company
    type_code: str = Field(max_length=40)
    number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    file_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    file_back_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    notes: str | None = Field(None, max_length=1000)


class DocumentOut(BaseModel):
    id: str
    type_code: str
    owner_type: str
    owner_id: str | None
    company_id: int
    number: str | None
    issue_date: date | None
    expiry_date: date | None
    has_file: bool
    has_back_file: bool
    notes: str | None
    is_current: bool
    created_at: datetime
    owner_name: dict | str | None = None  # in the expiring list: whose document it is


class RenewalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_code: str = Field(max_length=40)
    number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    expiry_date: date
    file_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class RenewalOut(BaseModel):
    id: str
    type_code: str
    type_name: dict | None
    driver: dict | None = None
    number: str | None
    expiry_date: date
    status: str  # pending | approved | rejected
    created_at: datetime
    decided_at: datetime | None
    note: str | None


class DriverDocumentOut(BaseModel):
    type_code: str
    type_name: dict
    number: str | None
    expiry_date: date | None
    days_left: int | None
    state: str  # valid | expiring | expired | missing
    renewable: bool
    renewal: RenewalOut | None


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)] | None = None
