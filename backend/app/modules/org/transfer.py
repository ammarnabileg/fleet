"""The org module's configuration in a transfer file (app.core.transfer): the settings sections, the companies, the
branches and the print templates. A company is known by its CR number, else by its name (any language)."""

import re
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.events import emit
from app.core.transfer import CREATED, UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, each, same
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.org import printing
from app.modules.org.models import Branch, Company, PrintTemplateVersion, Setting
from app.modules.org.schemas import SECTIONS, CompanyIn
from app.modules.org.service import COMPANY_FIELDS, SETTINGS_NAMESPACE, _cache

SHA = re.compile(r"^[0-9a-f]{64}$")
FILE_FIELDS = {"driver_app": ("splash_image",), "branding": ("logo_file",)}  # settings that name a stored file

# ------------------------------------------------------------------ company keys (used by other modules too)


def company_key(db: Session, company_id: int) -> dict | None:
    c = db.get(Company, company_id)
    return None if c is None else {"cr_number": c.cr_number, "name": c.name}


def _labels(c: Company) -> list[str]:
    return [*(c.name or {}).values(), *((c.trade_name or {}).values())]


def find_company(db: Session, key) -> Company | None:
    if not isinstance(key, dict):
        return None
    rows = list(db.scalars(select(Company).order_by(Company.id)))
    cr = (key.get("cr_number") or "").strip()
    if cr:
        found = next((c for c in rows if c.cr_number == cr), None)
        if found is not None:
            return found
    wanted = {" ".join(str(v).split()).casefold() for v in (key.get("name") or {}).values() if v}
    for c in rows:
        if cr and c.cr_number and c.cr_number != cr:
            continue  # another company that happens to carry the same name
        if wanted & {" ".join(x.split()).casefold() for x in _labels(c) if x}:
            return c
    return None


def company_id_for(db: Session, key) -> int:
    found = find_company(db, key)
    if found is None:
        raise AppError(422, "config_company_missing", company=_key_label(key))
    return found.id


def _key_label(key) -> str:
    if not isinstance(key, dict):
        return "?"
    names = key.get("name") or {}
    return key.get("cr_number") or names.get("ar") or names.get("en") or next(iter(names.values()), "?")


# ------------------------------------------------------------------ settings


def _export_settings(ctx: ExportContext) -> dict:
    out = {}
    for row in ctx.db.scalars(select(Setting).order_by(Setting.key)):
        model = SECTIONS.get(row.key)
        if model is None:
            continue
        value = model.model_validate(row.value).model_dump(mode="json")
        for f in FILE_FIELDS.get(row.key, ()):
            if value.get(f) and SHA.match(value[f]):
                value[f] = ctx.add_file(value[f])
        out[row.key] = value
    return out


def _apply_settings(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db
    if not isinstance(data, dict):
        report.skip("*", "config_section_invalid")
        return

    def one(item):
        name, value = item
        model = SECTIONS.get(name)
        if model is None:
            raise AppError(422, "unknown_settings_section", section=name)
        value = dict(value)
        for f in FILE_FIELDS.get(name, ()):
            if value.get(f) and SHA.match(str(value[f])) and not ctx.file(value[f]):
                report.warn(name, "config_file_missing", field=f)
                value[f] = None
                if name == "driver_app":
                    value["splash_enabled"] = False
        new = model.model_validate(value).model_dump(mode="json")
        row = db.get(Setting, name, with_for_update=True)
        before = None if row is None else model.model_validate(row.value).model_dump(mode="json")
        if row is not None and same(before, new):
            return UNCHANGED
        if row is None:
            row = Setting(key=name, value=new, version=1, updated_by=ctx.actor_user_id)
            db.add(row)
        else:
            row.value, row.version, row.updated_by, row.updated_at = new, row.version + 1, ctx.actor_user_id, func.now()
        db.flush()
        audit.record(
            db,
            action="settings.changed",
            entity_type="settings",
            entity_id=name,
            actor_user_id=ctx.actor_user_id,
            before=before,
            after=new,
            comment="config import",
        )
        emit(db, "settings.changed", uuid.uuid5(SETTINGS_NAMESPACE, name), {"section": name, "version": row.version})
        ctx.after_commit.append(lambda n=name: _cache.pop(n, None))
        return CREATED if before is None else UPDATED

    each(db, report, sorted(data.items()), lambda i: i[0], one)


# ------------------------------------------------------------------ companies


def _company_out(c: Company) -> dict:
    out = {f: getattr(c, f) for f in COMPANY_FIELDS}
    out["license_expiry"] = c.license_expiry.isoformat() if c.license_expiry else None
    return out


def _export_companies(ctx: ExportContext) -> list[dict]:
    return [_company_out(c) for c in ctx.db.scalars(select(Company).order_by(Company.id))]


def _apply_companies(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        clean = CompanyIn.model_validate({k: v for k, v in item.items() if k != "is_active"}).model_dump()
        clean["is_active"] = bool(item.get("is_active", True))
        clean["name"] = i18n.validate_localized(db, clean["name"])
        clean["trade_name"] = i18n.validate_localized(db, clean.get("trade_name"), required=False)
        company = find_company(db, {"cr_number": clean.get("cr_number"), "name": clean["name"]})
        if company is None:
            if clean.get("cr_number") and db.scalar(select(Company.id).where(Company.cr_number == clean["cr_number"])):
                raise AppError(409, "cr_number_taken")
            company = Company(**clean)
            db.add(company)
            db.flush()
            outcome = CREATED
        else:
            if same(_company_out(company), {**_company_out(company), **clean}):
                return UNCHANGED
            before = _company_out(company)
            if clean.get("cr_number") and clean["cr_number"] != company.cr_number:
                taken = db.scalar(
                    select(Company.id).where(Company.cr_number == clean["cr_number"], Company.id != company.id)
                )
                if taken:
                    raise AppError(409, "cr_number_taken")
            for f in COMPANY_FIELDS:
                if f in clean:
                    setattr(company, f, clean[f])
            company.version += 1
            company.updated_at = func.now()
            db.flush()
            outcome = UPDATED
            audit.record(
                db,
                action="company.updated",
                entity_type="company",
                entity_id=company.public_id,
                actor_user_id=ctx.actor_user_id,
                company_id=company.id,
                before=before,
                after=_company_out(company),
                comment="config import",
            )
        if outcome == CREATED:
            audit.record(
                db,
                action="company.created",
                entity_type="company",
                entity_id=company.public_id,
                actor_user_id=ctx.actor_user_id,
                company_id=company.id,
                after=_company_out(company),
                comment="config import",
            )
        return outcome

    each(db, report, data, lambda i: _key_label(i), one)


# ------------------------------------------------------------------ branches (the default branch is the default here)


def _export_branches(ctx: ExportContext) -> list[dict]:
    rows = ctx.db.scalars(select(Branch).order_by(Branch.is_default.desc(), Branch.id))
    return [{"name": b.name, "is_default": b.is_default, "is_active": b.is_active} for b in rows]


def _apply_branches(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        name = i18n.validate_localized(db, item["name"])
        rows = list(db.scalars(select(Branch).order_by(Branch.id)))
        if item.get("is_default"):
            branch = next((b for b in rows if b.is_default), None)
        else:
            wanted = {" ".join(v.split()).casefold() for v in name.values() if v}
            branch = next(
                (b for b in rows if wanted & {" ".join(v.split()).casefold() for v in (b.name or {}).values() if v}),
                None,
            )
        active = True if item.get("is_default") else bool(item.get("is_active", True))
        if branch is None:
            db.add(Branch(name=name, is_default=False, is_active=active))
            db.flush()
            return CREATED
        if same(branch.name, name) and branch.is_active == active:
            return UNCHANGED
        branch.name, branch.is_active = name, active if not branch.is_default else True
        branch.version += 1
        db.flush()
        return UPDATED

    each(db, report, data, lambda i: (i.get("name") or {}).get("ar") or "?", one)


# ------------------------------------------------------------------ print templates


def _template_files(ctx: ExportContext, t: dict) -> dict:
    t = {**t, "header": dict(t["header"]), "watermark": dict(t["watermark"])}
    t["header"]["logo"] = ctx.add_file(t["header"].get("logo"))
    t["watermark"]["image"] = ctx.add_file(t["watermark"].get("image"))
    return t


def _export_print(ctx: ExportContext) -> dict | None:
    version, config = printing.current(ctx.db)
    if version == 0:
        return None
    companies = []
    for cid, t in sorted(config["companies"].items(), key=lambda x: int(x[0])):
        key = company_key(ctx.db, int(cid))
        if key is not None:
            companies.append({"company": key, "template": _template_files(ctx, t)})
    return {"default": _template_files(ctx, config["default"]), "companies": companies}


def _clean_template(ctx: ImportContext, t: dict, label: str, report: Report) -> dict:
    t = {**t, "header": dict(t.get("header") or {}), "watermark": dict(t.get("watermark") or {})}
    for part, f in (("header", "logo"), ("watermark", "image")):
        if t[part].get(f) and not ctx.file(t[part][f]):
            report.warn(label, "config_file_missing", field=f"{part}.{f}")
            t[part][f] = None
    return printing.validate(ctx.db, t)


def _apply_print(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db
    if data is None:
        return
    if not isinstance(data, dict):
        report.skip("*", "config_section_invalid")
        return
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('org.print_templates', 0))"))
    version, config = printing.current(db)
    new = {"default": config["default"], "companies": dict(config["companies"])}

    def one_default(t):
        clean = _clean_template(ctx, t, "default", report)
        if same(clean, config["default"]) and version > 0:
            return UNCHANGED
        new["default"] = clean
        return UPDATED if version > 0 else CREATED

    def one_company(item):
        cid = str(company_id_for(db, item.get("company")))
        clean = _clean_template(ctx, item["template"], _key_label(item.get("company")), report)
        old = config["companies"].get(cid)
        if old is not None and same(clean, old):
            return UNCHANGED
        new["companies"][cid] = clean
        return CREATED if old is None else UPDATED

    sub = Report()
    each(db, sub, [data.get("default") or {}], lambda _: "default", one_default)
    each(db, sub, data.get("companies") or [], lambda i: _key_label(i.get("company")), one_company)
    report.created, report.updated, report.unchanged = sub.created, sub.updated, sub.unchanged
    report.skipped += sub.skipped
    if sub.changed:
        db.add(
            PrintTemplateVersion(
                version=version + 1, config=new, restored_from=None, changed="import", created_by=ctx.actor_user_id
            )
        )
        audit.record(
            db,
            action="print_template.published",
            entity_type="print_template",
            entity_id="import",
            actor_user_id=ctx.actor_user_id,
            after={"version": version + 1, "restored_from": None},
            comment="config import",
        )
        db.flush()


SECTIONS_OUT = [
    Section("companies", {"ar": "الشركات", "en": "Companies"}, _export_companies, _apply_companies, order=20),
    Section("branches", {"ar": "الفروع", "en": "Branches"}, _export_branches, _apply_branches, order=21),
    Section("settings", {"ar": "الإعدادات العامة", "en": "Settings"}, _export_settings, _apply_settings, order=80),
    Section("print_templates", {"ar": "قوالب الطباعة", "en": "Print templates"}, _export_print, _apply_print, order=85),
]
