"""The employment statuses (the office's list) in a transfer file, by code."""

from sqlalchemy import select

from app.core.transfer import ExportContext, ImportContext, Report, Section, columns, each, upsert_by
from app.modules.i18n import service as i18n
from app.modules.people.models import EmploymentStatus
from app.modules.people.schemas import StatusIn

FIELDS = ("name", "is_working", "is_terminal", "is_active", "sort_order")


def _export(ctx: ExportContext) -> list[dict]:
    rows = ctx.db.scalars(select(EmploymentStatus).order_by(EmploymentStatus.sort_order, EmploymentStatus.code))
    return [{"code": r.code} | columns(r, FIELDS) for r in rows]


def _apply(ctx: ImportContext, data, report: Report) -> None:
    def one(item):
        clean = StatusIn.model_validate({k: v for k, v in item.items() if k != "is_active"}).model_dump()
        values = {f: clean[f] for f in FIELDS if f in clean} | {"is_active": bool(item.get("is_active", True))}
        values["name"] = i18n.validate_localized(ctx.db, values["name"])
        return upsert_by(ctx.db, EmploymentStatus, {"code": clean["code"]}, values)

    each(ctx.db, report, data, lambda i: i.get("code"), one)


SECTIONS_OUT = [
    Section("employment_statuses", {"ar": "حالات التوظيف", "en": "Employment statuses"}, _export, _apply, order=22),
]
