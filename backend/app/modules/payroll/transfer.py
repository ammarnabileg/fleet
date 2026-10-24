"""The platforms (pay rule, salary sheet columns, daily and monthly fields) and the pay schemes with every version of
their terms or rule blocks, in a transfer file. A platform is known by its code, a scheme by its platform's code and
its own code, a version by the month it takes effect from."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.errors import AppError
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
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.payroll import forms, platforms, schemes
from app.modules.payroll.models import Platform, Scheme, SchemeVersion
from app.modules.payroll.month_models import PlatformForm
from app.modules.payroll.rules.engine import validate as validate_blocks
from app.modules.payroll.scheme_blocks import _sources
from app.modules.payroll.service import month_start

PLATFORM_FIELDS = ("name", "is_active", *platforms.RULE, "columns")
SCHEME_FIELDS = ("name", "description", "calculator", "driver_selectable", "is_active")
VERSION_FIELDS = (*schemes.TERMS_BY_VERSION, "steps", "blocks", "note")
PLATFORM_AMOUNTS = ("per_order", "per_hour", "per_valid_day", "invalid_day_amount")
SCHEME_AMOUNTS = ("per_order", "missing_order_rate", "reduced_rate")


def _decimals(values: dict, names) -> dict:
    for k in names:
        if values.get(k) is not None:
            values[k] = Decimal(str(values[k]))
    return values


# ------------------------------------------------------------------ platforms and their fields


def _form(db, p: Platform) -> dict:
    f = db.get(PlatformForm, p.id)
    return {"daily": list(f.daily), "monthly": list(f.monthly), "screenshot": f.screenshot} if f else None


def _export_platforms(ctx: ExportContext) -> list[dict]:
    rows = ctx.db.scalars(select(Platform).order_by(Platform.code))
    return [{"code": p.code} | columns(p, PLATFORM_FIELDS) | {"form": _form(ctx.db, p)} for p in rows]


def _apply_platforms(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        code = item["code"]
        values = {k: item[k] for k in PLATFORM_FIELDS if k in item}
        values = _decimals(platforms._tidy(values), PLATFORM_AMOUNTS)
        values["name"] = i18n.validate_localized(db, values["name"])
        values["columns"] = values.get("columns") or []
        p = db.scalar(select(Platform).where(Platform.code == code).with_for_update())
        merged = ({k: getattr(p, k) for k in platforms.RULE} if p else {}) | values
        platforms._check(merged)
        form = item.get("form")
        if form is not None:
            daily, monthly = forms._clean(db, form["daily"], "daily"), forms._clean(db, form["monthly"], "monthly")
            clash = {x["key"] for x in daily} & {x["key"] for x in monthly}
            if clash:
                raise AppError(422, "platform_field_duplicate", key=sorted(clash)[0])
            form = {"daily": daily, "monthly": monthly, "screenshot": form.get("screenshot")}
            values["daily_fields"] = [k for k in forms.DAILY_BUILTINS if k in {x["builtin"] for x in daily}]
        if p is None:
            p = Platform(code=code, **values)
            db.add(p)
            db.flush()
            outcome = CREATED
        else:
            current = columns(p, values)
            if same(current, values) and (form is None or same(_form(db, p), form)):
                return UNCHANGED
            for k, v in values.items():
                setattr(p, k, v)
            p.version += 1
            outcome = UPDATED
        if form is not None:
            f = db.get(PlatformForm, p.id)
            if f is None:
                f = PlatformForm(platform_id=p.id, version=0)
                db.add(f)
            if not same({"daily": f.daily, "monthly": f.monthly, "screenshot": f.screenshot}, form):
                f.daily, f.monthly, f.screenshot = form["daily"], form["monthly"], form["screenshot"]
                f.version = (f.version or 0) + 1
                f.updated_by = ctx.actor_user_id
        elif outcome == UPDATED:
            forms.sync_builtins(db, p)
        db.flush()
        audit.record(
            db,
            action="platform.created" if outcome == CREATED else "platform.updated",
            entity_type="platform",
            entity_id=p.public_id,
            actor_user_id=ctx.actor_user_id,
            after={"code": code, "import": True},
            comment="config import",
        )
        return outcome

    each(db, report, data, lambda i: i.get("code"), one)


# ------------------------------------------------------------------ schemes and their versions


def _version_out(v: SchemeVersion) -> dict:
    out = columns(v, VERSION_FIELDS)
    out["steps"] = schemes._steps_json(v.steps or [])
    out["company_covers"] = sorted(out.get("company_covers") or [])
    return {"effective_month": v.effective_month.isoformat()} | out


def _export_schemes(ctx: ExportContext) -> list[dict]:
    db = ctx.db
    codes = dict(db.execute(select(Platform.id, Platform.code)).tuples().all())
    rows = list(db.scalars(select(Scheme).order_by(Scheme.platform_id, Scheme.code)))
    versions = schemes._versions(db, [s.id for s in rows])
    return [
        {"platform": codes[s.platform_id], "code": s.code}
        | columns(s, SCHEME_FIELDS)
        | {"versions": [_version_out(v) for v in versions[s.id]]}
        for s in rows
    ]


def _clean_version(db, s_calc: str, platform_id: int, v: dict) -> dict:
    month = month_start(date.fromisoformat(str(v["effective_month"])[:10]))
    terms = _decimals({k: v.get(k) for k in schemes.TERMS_BY_VERSION}, SCHEME_AMOUNTS)
    terms["company_covers"] = sorted(terms.get("company_covers") or [])
    for k, default in (("target_orders", 420), ("required_valid_days", 28)):
        terms[k] = default if terms[k] is None else int(terms[k])
    for k in ("bonus_when_reduced", "marks_when_reduced"):
        terms[k] = bool(terms[k])
    terms["floor_at_zero"] = True if terms["floor_at_zero"] is None else bool(terms["floor_at_zero"])
    blocks = v.get("blocks")
    steps = schemes._steps_json(v.get("steps") or [])
    if blocks is not None:
        blocks = validate_blocks(blocks, sources={x["key"] for x in _sources(db, platform_id)})
        steps = []
    else:
        schemes._check({"calculator": s_calc, **terms, "steps": steps})
    return {"effective_month": month.isoformat()} | terms | {"steps": steps, "blocks": blocks, "note": v.get("note")}


def _apply_schemes(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        platform = db.scalar(select(Platform).where(Platform.code == item.get("platform")))
        if platform is None:
            raise AppError(422, "config_platform_missing", code=item.get("platform"))
        code = item["code"]
        meta = {k: item.get(k) for k in SCHEME_FIELDS}
        meta["name"] = i18n.validate_localized(db, meta["name"])
        meta["description"] = i18n.validate_localized(db, meta.get("description"), required=False)
        meta["driver_selectable"] = bool(meta.get("driver_selectable", True))
        meta["is_active"] = True if meta.get("is_active") is None else bool(meta["is_active"])
        if meta["calculator"] not in schemes.STEP_KINDS:
            raise AppError(422, "config_item_invalid", field="calculator", detail=str(meta["calculator"]))
        wanted = sorted(
            (_clean_version(db, meta["calculator"], platform.id, v) for v in item.get("versions") or []),
            key=lambda v: v["effective_month"],
        )
        if not wanted:
            raise AppError(422, "config_item_invalid", field="versions", detail="empty")
        s = db.scalar(select(Scheme).where(Scheme.platform_id == platform.id, Scheme.code == code).with_for_update())
        created = s is None
        if created:
            newest = wanted[-1]
            s = Scheme(
                platform_id=platform.id,
                code=code,
                created_by=ctx.actor_user_id or 0,
                **meta,
                **{k: newest[k] for k in schemes.TERMS_BY_VERSION},
            )
            db.add(s)
            db.flush()
        elif meta["calculator"] != s.calculator and schemes._used_ids(db, [s.id]):
            raise AppError(409, "scheme_in_use")
        changed = created or not same(columns(s, SCHEME_FIELDS), meta)
        for k, v in meta.items():
            setattr(s, k, v)
        have = {v.effective_month.isoformat(): v for v in schemes._versions(db, [s.id], lock=True)[s.id]}
        paid = schemes._last_paid(db, [s.id]).get(s.id)
        next_no = max((v.version_no for v in have.values()), default=0) + 1
        for v in wanted:
            old = have.get(v["effective_month"])
            if old is not None and same(_version_out(old), v):
                continue
            if paid is not None and date.fromisoformat(v["effective_month"]) <= paid:
                report.warn(f"{platform.code}/{code}", "scheme_version_month", **{"from": v["effective_month"][:7]})
                continue
            values = {k: v[k] for k in VERSION_FIELDS}
            if old is None:
                db.add(
                    SchemeVersion(
                        scheme_id=s.id,
                        version_no=next_no,
                        effective_month=date.fromisoformat(v["effective_month"]),
                        created_by=ctx.actor_user_id,
                        **values,
                    )
                )
                next_no += 1
            else:
                for k, val in values.items():
                    setattr(old, k, val)
            changed = True
        if not changed:
            return UNCHANGED
        db.flush()
        newest = schemes._versions(db, [s.id])[s.id][-1]
        schemes._mirror(db, s, schemes._terms(newest))
        if newest.blocks is not None:
            s.calculator = "blocks"
        if not created:
            s.version += 1
        db.flush()
        audit.record(
            db,
            action="scheme.created" if created else "scheme.updated",
            entity_type="scheme",
            entity_id=s.public_id,
            actor_user_id=ctx.actor_user_id,
            after={"platform": platform.code, "code": code, "versions": len(wanted), "import": True},
            comment="config import",
        )
        return CREATED if created else UPDATED

    each(db, report, data, lambda i: f"{i.get('platform')}/{i.get('code')}", one)


SECTIONS_OUT = [
    Section(
        "platforms",
        {"ar": "المنصات وحقولها اليومية والشهرية", "en": "Platforms and their daily and monthly fields"},
        _export_platforms,
        _apply_platforms,
        order=45,
    ),
    Section(
        "pay_schemes",
        {"ar": "أنظمة الرواتب ونسخها وقواعدها", "en": "Pay schemes, their versions and rules"},
        _export_schemes,
        _apply_schemes,
        order=46,
    ),
]
