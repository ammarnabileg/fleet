"""The leave types' rules in a transfer file, by code. The kinds of leave are the product's (the code knows each):
an import updates the rules of the kinds this installation has and skips a kind it does not know."""

from sqlalchemy import select

from app.core.clock import utcnow
from app.core.errors import AppError
from app.core.transfer import UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, columns, each, same
from app.modules.attendance.leaves import _check_tiers
from app.modules.attendance.models import LeaveType
from app.modules.attendance.schemas import LeaveTypeIn
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n

FIELDS = (
    "name",
    "legal_ref",
    "tiers",
    "tier_period",
    "max_per_occurrence",
    "max_per_year",
    "max_per_service",
    "min_service_months",
    "once_per_service",
    "requires_attachment",
    "eligible_gender",
    "counts",
    "accrues",
    "office_may_pay",
    "driver_may_request",
    "active",
    "sort_order",
)


def _export(ctx: ExportContext) -> list[dict]:
    rows = ctx.db.scalars(select(LeaveType).order_by(LeaveType.sort_order, LeaveType.code))
    return [{"code": r.code} | columns(r, FIELDS) for r in rows]


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        t = db.scalar(select(LeaveType).where(LeaveType.code == item["code"]).with_for_update())
        if t is None:
            raise AppError(404, "leave_type_not_found")
        clean = LeaveTypeIn.model_validate({k: item.get(k) for k in FIELDS} | {"version": 0}).model_dump()
        values = {k: clean[k] for k in FIELDS if clean.get(k) is not None or k in NULLABLE}
        values["name"] = i18n.validate_localized(db, values.get("name") or t.name)
        _check_tiers(values.get("tiers") or t.tiers)
        before = columns(t, FIELDS)
        if same(before, before | values):
            return UNCHANGED
        for k, v in values.items():
            setattr(t, k, v)
        t.version += 1
        t.updated_by, t.updated_at = ctx.actor_user_id, utcnow()
        db.flush()
        audit.record(
            db,
            action="leave_type.updated",
            entity_type="leave_type",
            entity_id=t.code,
            actor_user_id=ctx.actor_user_id,
            before=before,
            after=columns(t, FIELDS),
            comment="config import",
        )
        return UPDATED

    each(db, report, data, lambda i: i.get("code"), one)


NULLABLE = ("legal_ref", "max_per_occurrence", "max_per_year", "max_per_service", "eligible_gender")

SECTIONS_OUT = [Section("leave_types", {"ar": "أنواع الإجازات", "en": "Leave types"}, _export, _apply, order=24)]
