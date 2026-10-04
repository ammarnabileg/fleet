from pydantic import BaseModel, ConfigDict, Field

from app.core.types import LangCode


class LanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name_native: str
    name_en: str
    direction: str
    is_default: bool


class LanguageAdminOut(LanguageOut):
    fallback_code: str | None
    is_active: bool
    sort_order: int
    version: int


class LanguageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: LangCode
    name_native: str = Field(min_length=2, max_length=50)
    name_en: str = Field(min_length=2, max_length=50)
    direction: str = Field(pattern="^(rtl|ltr)$")
    fallback_code: LangCode | None = None
    sort_order: int = Field(100, ge=0, le=1000)


class LanguageUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name_native: str | None = Field(default=None, min_length=2, max_length=50)
    name_en: str | None = Field(default=None, min_length=2, max_length=50)
    direction: str | None = Field(default=None, pattern="^(rtl|ltr)$")
    fallback_code: LangCode | None = None
    is_active: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class CatalogOut(BaseModel):
    lang: str
    direction: str
    revision: int
    messages: dict[str, dict[str, str]]


class EntryOut(BaseModel):
    namespace: str
    key: str
    reference: str  # text in the default language, for the translator
    base: str | None  # shipped with the code for this language
    override: str | None  # saved from the settings screen


class OverrideItem(BaseModel):
    namespace: str = Field(min_length=1, max_length=50)
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)


class OverridesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OverrideItem] = Field(min_length=1, max_length=2000)
