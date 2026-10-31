"""The document types in a transfer file, by code."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app.core.transfer import ExportContext, ImportContext, Report, Section, columns, each, upsert_by
from app.core.types import LocalizedText
from app.modules.documents.models import DocumentType
from app.modules.i18n import service as i18n

FIELDS = ("name", "applies_to", "requires_expiry", "is_active", "sort_order")


class TypeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
    name: LocalizedText
    applies_to: Literal["employee", "vehicle", "company"]
    requires_expiry: bool = True
    is_active: bool = True
    sort_order: int = Field(100, ge=0, le=10000)


def _export(ctx: ExportContext) -> list[dict]:
    rows = ctx.db.scalars(select(DocumentType).order_by(DocumentType.sort_order, DocumentType.code))
    return [{"code": r.code} | columns(r, FIELDS) for r in rows]


def _apply(ctx: ImportContext, data, report: Report) -> None:
    def one(item):
        clean = TypeIn.model_validate(item).model_dump()
        values = {f: clean[f] for f in FIELDS}
        values["name"] = i18n.validate_localized(ctx.db, values["name"])
        return upsert_by(ctx.db, DocumentType, {"code": clean["code"]}, values)

    each(ctx.db, report, data, lambda i: i.get("code"), one)


SECTIONS_OUT = [Section("document_types", {"ar": "أنواع المستندات", "en": "Document types"}, _export, _apply, order=23)]
