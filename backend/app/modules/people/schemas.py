import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import Iban, LocalizedText

Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+[1-9][0-9]{7,14}$")]
CivilId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{12}$")]
Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Salary = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class StatusOut(BaseModel):
    code: str
    name: dict[str, str]
    is_working: bool
    is_terminal: bool
    is_active: bool
    sort_order: int


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: LocalizedText
    is_working: bool = False
    is_terminal: bool = False
    sort_order: int = Field(100, ge=0, le=10000)


class StatusUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LocalizedText | None = None
    is_working: bool | None = None
    is_terminal: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(None, ge=0, le=10000)


class NationalityOut(BaseModel):
    value: str  # what the record keeps
    ar: str
    en: str


class EmployeeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_number: Short
    name: LocalizedText
    civil_id: CivilId | None = None
    nationality: Short | None = None
    company_id: int
    branch_id: int | None = None  # the main branch when omitted
    department: Short | None = None
    job_title: Short | None = None
    is_driver: bool = False
    phone: Phone | None = None
    hire_date: date | None = None
    status_code: Code | None = None  # "active" when omitted
    basic_salary: Salary | None = None
    iban: Iban | None = None
    bank_name: Short | None = None
    payment_method: Literal["bank", "cash"] | None = None
    platform_id: int | None = None  # the delivery platform he works on (payroll)
    platform_driver_id: Short | None = None  # his ID on that platform
    fuel_card: bool = False  # his fuel is on a company card (topped up as one expense): he claims no fuel


class EmployeeUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    employee_number: Short | None = None
    name: LocalizedText | None = None
    civil_id: CivilId | None = None
    nationality: Short | None = None
    company_id: int | None = None
    branch_id: int | None = None
    department: Short | None = None
    job_title: Short | None = None
    is_driver: bool | None = None
    phone: Phone | None = None
    hire_date: date | None = None
    basic_salary: Salary | None = None
    iban: Iban | None = None
    bank_name: Short | None = None
    payment_method: Literal["bank", "cash"] | None = None
    platform_id: int | None = None
    platform_driver_id: Short | None = None
    fuel_card: bool | None = None


class PlatformAssignIn(BaseModel):
    """The drivers chosen in the list, put on one delivery platform (or on none) at once."""

    model_config = ConfigDict(extra="forbid")

    employee_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    platform_id: int | None


class PlatformAssignOut(BaseModel):
    updated: int
    unchanged: int  # already on it
    skipped: int  # not drivers


class EmployeeOut(BaseModel):
    id: str
    employee_number: str
    name: dict[str, str]
    civil_id: str | None
    nationality: str | None
    company_id: int
    branch_id: int
    department: str | None
    job_title: str | None
    is_driver: bool
    phone: str | None
    hire_date: date | None
    status_code: str
    status_name: dict[str, str]
    is_terminal: bool
    app_access: str
    basic_salary: Decimal | None  # null without employees.view_salary, like the bank details
    iban: str | None
    bank_name: str | None
    payment_method: str | None
    platform_id: int | None
    platform_driver_id: str | None
    fuel_card: bool = False
    version: int


class StatusChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_code: Code
    note: str | None = Field(None, max_length=500)


class AppAccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_access: Literal["active", "suspended"]


class StatusHistoryOut(BaseModel):
    status_code: str
    changed_at: datetime
    changed_by: int | None
    note: str | None


class ExternalRefIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProfileOut(BaseModel):
    name: dict
    employee_number: str
    phone: str | None
    civil_id: str | None
    nationality: str | None
    job_title: str | None
    hire_date: date | None
    company: dict | None
    branch: dict | None
    platform: dict | None
    platform_driver_id: str | None
    bank_name: str | None
    iban_last4: str | None
    payment_method: str | None
    fuel_card: bool = False


class EmployeeFacetsOut(BaseModel):
    departments: list[str]
    job_titles: list[str]
