"""The driver status templates in force (the latest published set) in a transfer file, by template code. A
template meant for some companies names them by CR number / name. An import that changes any template publishes
the set as a new version (the history and «back to the previous setting» keep working)."""

from sqlalchemy import text

from app.core import live
from app.core.errors import AppError
from app.core.transfer import CREATED, UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, each, same
from app.modules.audit import service as audit
from app.modules.driver_status import templates as tpl
from app.modules.driver_status.models import ConfigVersion
from app.modules.driver_status.service import current
from app.modules.org import service as org
from app.modules.org import transfer as org_transfer


def _export(ctx: ExportContext) -> dict | None:
    version, templates = current(ctx.db)
    if version == 0:
        return None
    out = {}
    for code, t in sorted(templates.items()):
        t = dict(t)
        keys = [org_transfer.company_key(ctx.db, int(c)) for c in t.pop("company_ids", []) or []]
        out[code] = t | {"companies": [k for k in keys if k is not None]}
    return out


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db
    if data is None:
        return
    if not isinstance(data, dict):
        report.skip("*", "config_section_invalid")
        return
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('driver_status.config', 0))"))
    version, templates = current(db)
    new = dict(templates)

    def one(item):
        code, t = item
        t = dict(t)
        ids = [org_transfer.company_id_for(db, k) for k in t.pop("companies", []) or []]
        try:
            clean = tpl.validate(code, t | {"company_ids": ids}, None)
        except tpl.TemplateError as e:
            raise AppError(422, e.code, **e.params) from None
        if version > 0 and same(templates.get(code), clean):
            return UNCHANGED
        new[code] = clean
        return UPDATED if version > 0 else CREATED

    each(db, report, sorted(data.items()), lambda i: i[0], one)
    if not report.changed:
        return
    db.add(
        ConfigVersion(
            version=version + 1, templates=new, restored_from=None, changed="import", created_by=ctx.actor_user_id
        )
    )
    audit.record(
        db,
        action="driver_status.published",
        entity_type="status_template",
        entity_id="import",
        actor_user_id=ctx.actor_user_id,
        after={"version": version + 1, "restored_from": None},
        comment="config import",
    )
    db.flush()
    ids = {c["id"] for c in org.list_companies(db, all_companies=True, company_ids=())}

    def tell_apps():
        for c in ids:
            live.broker().publish(c, {"event": "driver_status", "data": {"config": True}})

    ctx.after_commit.append(tell_apps)


SECTIONS_OUT = [
    Section("driver_status", {"ar": "قوالب حالة السائق", "en": "Driver status templates"}, _export, _apply, order=86)
]
