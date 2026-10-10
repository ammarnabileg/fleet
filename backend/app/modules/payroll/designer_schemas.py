"""Request bodies of the rules designer, the platform's fields and the month inputs."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import LocalizedText

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class FieldOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Key
    label: LocalizedText


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Key
    label: LocalizedText
    type: Literal["int", "money", "bool", "choice", "batch_orders", "task_counts"] = "int"
    builtin: str | None = None  # orders | cash | valid_day; attendance_marks | star_day_failed | ... | task_counts
    required: bool = False
    help: LocalizedText | None = None
    options: list[FieldOption] = Field(default_factory=list, max_length=30)


class FieldsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    daily: list[FieldIn] = Field(default_factory=list, max_length=30)
    monthly: list[FieldIn] = Field(default_factory=list, max_length=30)
    screenshot: bool | None = None  # None: the global setting


class BatchRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch: int = Field(ge=1, le=20)
    orders: int = Field(ge=0, le=100000)


class MonthValuesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: date
    values: dict[Key, bool | int | Decimal | None] = Field(default_factory=dict, max_length=40)
    batches: list[BatchRow] | None = Field(None, max_length=20)  # sent: replaces his batch rows for the month
    tasks: dict[Key, Annotated[int, Field(ge=0, le=100000)]] | None = None


class ExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str
    month: date
    kind: Literal["accepted_excuse", "company_error", "exception_day"]
    days: int = Field(0, ge=0, le=31)
    corrections: dict[Key, bool | int | Decimal] = Field(default_factory=dict, max_length=20)
    note: Note


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Note


class BlocksIn(BaseModel):
    """A list of rule blocks, checked by the engine (rules/engine.py validate)."""

    model_config = ConfigDict(extra="forbid")

    blocks: list[dict] = Field(max_length=60)
    floor_at_zero: bool = True


class PreviewIn(BlocksIn):
    platform_id: int | None = None
    month: dict = Field(default_factory=dict)  # sample figures: orders, valid_days, marks, batches, fields...


class SchemeBlocksIn(BlocksIn):
    version: int
    effective_month: date | None = None  # «يسري من»; none: a scheme nobody was paid on is redefined
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class FromTemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_id: int
    template: Key | None = None  # none: a single price per order to edit
    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
    name: LocalizedText
    driver_selectable: bool = True
