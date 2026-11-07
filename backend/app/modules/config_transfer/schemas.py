from pydantic import BaseModel, ConfigDict, Field


class SectionOut(BaseModel):
    key: str
    label: dict
    has_secrets: bool


class ExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[str] = Field(default_factory=list, max_length=50)  # none: every section
    include_secrets: bool = False
    passphrase: str | None = Field(None, max_length=200)  # required with include_secrets


class ItemNote(BaseModel):
    item: str
    code: str
    params: dict


class SectionReport(BaseModel):
    key: str
    label: dict
    created: int
    updated: int
    unchanged: int
    skipped: list[ItemNote]
    warnings: list[ItemNote]


class ImportOut(BaseModel):
    dry_run: bool
    format_version: int
    source: str | None
    exported_at: str | None
    app_version: str | None
    secrets: str  # none | used | skipped (the file has them, no passphrase was given)
    unknown_sections: list[str]
    sections: list[SectionReport]
