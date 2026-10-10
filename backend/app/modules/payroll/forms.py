"""A platform's input fields, set in the dashboard, not in code: what the driver fills in the app each day and what the
office enters or imports each month. The built-in daily fields (orders, cash, valid day) keep their report columns, so
an app that knows only those keeps working; any other field is the platform's own, stored by its key.

The rule blocks read these fields: a count field as a block's source (price per unit, tiers, overage), a yes/no field
in a condition. A daily field's month total is the sum of its numbers, or the days answered yes."""

import re
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.payroll.models import Platform
from app.modules.payroll.month_models import PlatformForm

DAILY_BUILTINS = {"orders": "int", "cash": "money", "valid_day": "bool"}
MONTHLY_BUILTINS = {
    "attendance_marks": "int",
    "star_day_failed": "bool",
    "late_count": "int",
    "absent_days": "int",
    "batch_orders": "batch_orders",
    "task_counts": "task_counts",
}
CUSTOM_TYPES = ("int", "money", "bool", "choice")
# names the month's figures already use: a field of the platform cannot take them
RESERVED = {
    *DAILY_BUILTINS,
    *MONTHLY_BUILTINS,
    "valid_days",
    "working_days",
    "hours",
    "batches",
    "batch_level",
    "tasks",
    "fields",
    "basic_salary",
    "personal_rate",
    "month_invalid",
}
KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_FIELDS = 30


def _label(db: Session, ns: str, key: str) -> dict:
    out = {}
    for lang in ("ar", "en"):
        out[lang] = i18n.base_catalog(lang).get(ns, {}).get(key, key)
    return out


def builtin_item(db: Session, key: str) -> dict:
    return {
        "key": key,
        "label": _label(db, "daily_field", key),
        "type": DAILY_BUILTINS[key],
        "builtin": key,
        "required": True,
        "help": None,
        "options": [],
    }


def _default_daily(db: Session, p: Platform) -> list[dict]:
    """A platform never set up here asks what its daily_fields say, as before."""
    return [builtin_item(db, k) for k in DAILY_BUILTINS if k in (p.daily_fields or [])]


def get(db: Session, platform_id: int) -> dict:
    p = db.get(Platform, platform_id)
    if p is None:
        raise AppError(404, "platform_not_found")
    f = db.get(PlatformForm, platform_id)
    return {
        "platform_id": platform_id,
        "daily": list(f.daily) if f else _default_daily(db, p),
        "monthly": list(f.monthly) if f else [],
        "screenshot": f.screenshot if f else None,
        "version": f.version if f else 0,
    }


def _clean(db: Session, items: list[dict], scope: str) -> list[dict]:
    builtins = DAILY_BUILTINS if scope == "daily" else MONTHLY_BUILTINS
    if len(items) > MAX_FIELDS:
        raise AppError(422, "platform_field_invalid", key="*")
    out, seen = [], set()
    for it in items:
        key, builtin = it["key"], it.get("builtin")
        if builtin is not None:
            if builtin not in builtins or key != builtin:
                raise AppError(422, "platform_field_invalid", key=key)
            kind = builtins[builtin]
        else:
            kind = it["type"]
            if not KEY.match(key) or key in RESERVED or kind not in CUSTOM_TYPES:
                raise AppError(422, "platform_field_invalid", key=key)
        if key in seen:
            raise AppError(422, "platform_field_duplicate", key=key)
        seen.add(key)
        options = []
        if kind in ("choice", "task_counts"):
            for o in it.get("options") or []:
                if not KEY.match(o["value"]):
                    raise AppError(422, "platform_field_invalid", key=key)
                options.append({"value": o["value"], "label": i18n.validate_localized(db, o["label"])})
            if not options or len({o["value"] for o in options}) != len(options):
                raise AppError(422, "platform_field_invalid", key=key)
        out.append(
            {
                "key": key,
                "label": i18n.validate_localized(db, it["label"]),
                "type": kind,
                "builtin": builtin,
                "required": bool(it.get("required")),
                "help": i18n.validate_localized(db, it["help"]) if it.get("help") else None,
                "options": options,
            }
        )
    return out


def save(db: Session, platform_id: int, data: dict, *, version: int, actor_user_id: int) -> dict:
    """The platform's fields as a whole; its daily_fields follow the built-in ones, for the apps that know only
    those."""
    p = db.get(Platform, platform_id, with_for_update=True)
    if p is None:
        raise AppError(404, "platform_not_found")
    f = db.get(PlatformForm, platform_id)
    if (f.version if f else 0) != version:
        raise AppError(409, "version_conflict")
    daily, monthly = _clean(db, data["daily"], "daily"), _clean(db, data["monthly"], "monthly")
    clash = {x["key"] for x in daily} & {x["key"] for x in monthly}
    if clash:
        raise AppError(422, "platform_field_duplicate", key=sorted(clash)[0])
    before = get(db, platform_id)
    if f is None:
        f = PlatformForm(platform_id=platform_id, version=0)
        db.add(f)
    f.daily, f.monthly, f.screenshot = daily, monthly, data.get("screenshot")
    f.version += 1
    f.updated_by, f.updated_at = actor_user_id, utcnow()
    p.daily_fields = [k for k in DAILY_BUILTINS if k in {x["builtin"] for x in daily}]
    p.version += 1
    db.flush()
    audit.record(
        db,
        action="platform.fields_set",
        entity_type="platform",
        entity_id=p.public_id,
        actor_user_id=actor_user_id,
        before={"daily": [x["key"] for x in before["daily"]], "monthly": [x["key"] for x in before["monthly"]]},
        after={"daily": [x["key"] for x in daily], "monthly": [x["key"] for x in monthly], "screenshot": f.screenshot},
    )
    db.commit()
    return get(db, platform_id)


# ------------------------------------------------------------------ what other parts read


def daily_items(db: Session, platform_id: int | None) -> list[dict] | None:
    if not platform_id or db.get(Platform, platform_id) is None:
        return None
    return get(db, platform_id)["daily"]


def daily_screenshot(db: Session, platform_id: int | None) -> bool | None:
    f = db.get(PlatformForm, platform_id) if platform_id else None
    return f.screenshot if f else None


def _value(kind: str, raw, options: list[dict]):
    if kind == "bool":
        if not isinstance(raw, bool):
            raise ValueError
        return raw
    if kind == "choice":
        if raw not in {o["value"] for o in options}:
            raise ValueError
        return raw
    if isinstance(raw, bool):
        raise ValueError
    d = Decimal(str(raw))
    if kind == "int":
        if d != d.to_integral_value() or d < 0 or d > 100000:
            raise ValueError
        return int(d)
    if d < 0 or d >= Decimal("1000000") or d != d.quantize(Decimal("0.001")):  # money
        raise ValueError
    return str(d.quantize(Decimal("0.001")))


def check_daily_extra(db: Session, platform_id: int | None, extra: dict | None, *, partial: bool = False) -> dict:
    """The platform's own daily fields the driver sent, checked and as stored. An app that sends none (an older one)
    sends only the built-in fields, and is not refused for the others; `partial`: an edit, only what is sent."""
    items = [x for x in (daily_items(db, platform_id) or []) if not x.get("builtin")]
    if extra is None:
        return {}
    known = {x["key"]: x for x in items}
    unknown = sorted(set(extra) - set(known))
    if unknown:
        raise AppError(422, "field_unknown", field=unknown[0])
    out = {}
    for key, it in known.items():
        raw = extra.get(key)
        if raw is None or raw == "":
            if it["required"] and not partial:
                raise AppError(422, "field_required", field=key)
            continue
        try:
            out[key] = _value(it["type"], raw, it["options"])
        except (ValueError, InvalidOperation, TypeError):
            raise AppError(422, "field_invalid", field=key) from None
    return out


def month_totals(items: list[dict], reports: list[tuple]) -> dict:
    """A daily field's month: the sum of its numbers, or the days answered yes (a day with several sessions once)."""
    out = {}
    for it in items:
        if it.get("builtin") or it["type"] == "choice":
            continue
        key = it["key"]
        if it["type"] == "bool":
            out[key] = len({day for day, extra in reports if extra.get(key) is True})
        else:
            out[key] = sum((Decimal(str(extra[key])) for _, extra in reports if extra.get(key) is not None), Decimal(0))
    return out


def sources(db: Session, platform_id: int | None) -> set[str]:
    """The platform's fields a rule block may read: its own daily and monthly fields (numbers, and yes/no days)."""
    if not platform_id:
        return set()
    f = get(db, platform_id)
    return {x["key"] for x in f["daily"] + f["monthly"] if not x.get("builtin") and x["type"] != "choice"}
