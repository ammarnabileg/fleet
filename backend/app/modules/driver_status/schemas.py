import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class Localized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ar: str = Field("", max_length=200)
    en: str = Field("", max_length=200)


class TemplateIn(BaseModel):
    """Checked in full by templates.validate (the lists the app supports); here only the shape."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=40)
    name: Localized
    icon: str = Field(max_length=40)
    color: str = Field(max_length=7)
    title: Localized
    subtitle: Localized
    priority: int
    visibility: str = Field(max_length=40)
    ttl_minutes: int | None = None
    audience: str = Field("all", max_length=20)
    company_ids: list[int] = Field(default_factory=list, max_length=200)
    actions: list[str] = Field(default_factory=list, max_length=10)
    active: bool = True


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: TemplateIn
    config_version: int = Field(ge=0)  # the version the editor started from: a newer publish meanwhile is refused


class RollbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: int = Field(ge=0)


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=40)
    template: TemplateIn
    lang: Literal["ar", "en"] = "ar"
    values: dict[str, Annotated[str, StringConstraints(max_length=60)]] | None = None


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: uuid.UUID
    message: Message
    reason: Reason | None = None


class AckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_ref: uuid.UUID
