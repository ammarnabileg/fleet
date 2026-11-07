"""The maintenance centers in a transfer file, by name (case ignored). Their portal accounts are people with
passwords: not exported; they are made again on the new installation."""

from sqlalchemy import func, select

from app.core.transfer import (
    CREATED,
    UNCHANGED,
    UPDATED,
    ExportContext,
    ImportContext,
    Report,
    Section,
    columns,
    each,
    same,
)
from app.modules.maintenance.models import Center
from app.modules.maintenance.schemas import CenterIn

FIELDS = ("specialty", "contact_name", "phone", "email", "address", "notes", "is_active")


def _export(ctx: ExportContext) -> list[dict]:
    return [{"name": c.name} | columns(c, FIELDS) for c in ctx.db.scalars(select(Center).order_by(Center.name))]


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        clean = CenterIn.model_validate(item).model_dump()
        c = db.scalar(select(Center).where(func.lower(Center.name) == clean["name"].lower()).with_for_update())
        if c is None:
            db.add(Center(**clean))
            db.flush()
            return CREATED
        values = {k: clean[k] for k in ("name", *FIELDS)}
        if same(columns(c, values), values):
            return UNCHANGED
        for k, v in values.items():
            setattr(c, k, v)
        c.version += 1
        c.updated_at = func.now()
        db.flush()
        return UPDATED

    each(db, report, data, lambda i: i.get("name"), one)


SECTIONS_OUT = [
    Section("maintenance_centers", {"ar": "مراكز الصيانة", "en": "Maintenance centers"}, _export, _apply, order=60)
]
