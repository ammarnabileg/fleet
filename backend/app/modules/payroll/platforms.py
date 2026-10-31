"""Delivery platforms as data: each has its pay rule and its salary sheet, set from the control panel (the sheet is
read from the client's own template). No platform is known to the code."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.payroll.columns import BY_CODE
from app.modules.payroll.models import Platform
from app.modules.people import service as people

RULE = (
    "driver_fields",
    "daily_fields",
    "pay_basic",
    "per_order",
    "per_hour",
    "per_valid_day",
    "invalid_days",
    "invalid_day_amount",
    "day_divisor",
)


def _out(p: Platform, counts: dict) -> dict:
    return {
        "id": p.id,
        "public_id": str(p.public_id),
        "code": p.code,
        "name": p.name,
        "is_active": p.is_active,
        "driver_fields": list(p.driver_fields),
        "daily_fields": list(p.daily_fields),
        "pay_basic": p.pay_basic,
        "per_order": p.per_order,
        "per_hour": p.per_hour,
        "per_valid_day": p.per_valid_day,
        "invalid_days": p.invalid_days,
        "invalid_day_amount": p.invalid_day_amount,
        "day_divisor": p.day_divisor,
        "columns": p.columns,
        "drivers": counts.get(p.id, 0),
        "is_core": p.is_core,
        "version": p.version,
    }


DAILY = ("orders", "cash", "valid_day")


def _tidy(data: dict) -> dict:
    """Each daily field once, in the order the app asks for them."""
    if data.get("daily_fields") is not None:
        data["daily_fields"] = [f for f in DAILY if f in data["daily_fields"]]
    return data


def _check(data: dict) -> None:
    unknown = sorted({c["code"] for c in data.get("columns") or []} - set(BY_CODE))
    if unknown:
        raise AppError(422, "unknown_column", codes=", ".join(unknown))
    if data.get("invalid_days") == "fixed" and data.get("invalid_day_amount") is None:
        raise AppError(422, "field_required", field="invalid_day_amount")


def list_platforms(db: Session) -> list[dict]:
    counts = people.platform_counts(db)
    q = select(Platform).order_by(Platform.is_core.desc(), Platform.is_active.desc(), Platform.id)
    return [_out(p, counts) for p in db.scalars(q)]


def get(db: Session, platform_id: int | None) -> Platform | None:
    return db.get(Platform, platform_id) if platform_id else None


def all_by_id(db: Session) -> dict[int, Platform]:
    return {p.id: p for p in db.scalars(select(Platform))}


def create(db: Session, data: dict, *, actor_user_id: int) -> dict:
    _check(_tidy(data))
    data = {**data, "name": i18n.validate_localized(db, data["name"])}
    p = Platform(**data)
    db.add(p)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "platforms_code_key":
            raise
        raise AppError(409, "platform_code_taken") from None
    db.refresh(p)
    audit.record(
        db,
        action="platform.created",
        entity_type="platform",
        entity_id=p.public_id,
        actor_user_id=actor_user_id,
        after={k: data[k] for k in ("code", "name", *RULE) if k in data} | {"columns": len(p.columns)},
    )
    db.commit()
    return _out(p, {})


def update(db: Session, platform_id: int, *, version: int, changes: dict, actor_user_id: int) -> dict:
    p = db.get(Platform, platform_id, with_for_update=True)
    if p is None:
        raise AppError(404, "platform_not_found")
    if p.version != version:
        raise AppError(409, "version_conflict")
    merged = {k: getattr(p, k) for k in RULE} | _tidy(changes)
    _check(merged)
    if "name" in changes:
        changes["name"] = i18n.validate_localized(db, changes["name"])
    before = {k: getattr(p, k) for k in changes if k != "columns"}
    for k, v in changes.items():
        setattr(p, k, v)
    p.version += 1
    if "daily_fields" in changes:  # the platform's field list follows its built-in daily fields
        from app.modules.payroll import forms

        forms.sync_builtins(db, p)
    db.flush()
    audit.record(
        db,
        action="platform.updated",
        entity_type="platform",
        entity_id=p.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after={k: v for k, v in changes.items() if k != "columns"}
        | ({"columns": len(p.columns)} if "columns" in changes else {}),
    )
    db.commit()
    return _out(p, people.platform_counts(db))


def delete(db: Session, platform_id: int, *, actor_user_id: int) -> None:
    """A platform added by hand, never used (no driver, scheme, statement or month data on it): removed. The core
    platforms stay."""
    p = db.get(Platform, platform_id, with_for_update=True)
    if p is None:
        raise AppError(404, "platform_not_found")
    if p.is_core:
        raise AppError(409, "platform_core")
    snapshot = {"code": p.code, "name": p.name}
    try:
        with db.begin_nested():
            db.delete(p)
            db.flush()
    except IntegrityError:
        raise AppError(409, "platform_in_use") from None
    audit.record(
        db,
        action="platform.deleted",
        entity_type="platform",
        entity_id=p.public_id,
        actor_user_id=actor_user_id,
        before=snapshot,
    )
    db.commit()


def _platform(db: Session, platform_id: int) -> Platform:
    p = db.get(Platform, platform_id)
    if p is None:
        raise AppError(404, "platform_not_found")
    return p


def drivers(db: Session, platform_id: int, *, missing: bool = False, **scope) -> list[dict]:
    """The platform's drivers (still at work) with their ID on it; `missing`: those with none yet."""
    from app.modules.payroll import schemes
    from app.modules.payroll.service import month_start

    _platform(db, platform_id)
    rows = [x for x in people.platform_profiles(db, platform_id, **scope) if x["platform_id"] == platform_id]
    if missing:
        rows = [x for x in rows if not x["platform_driver_id"]]
    on = schemes.for_month(db, [x["id"] for x in rows], month_start(today()))
    return [
        {
            "id": x["public_id"],
            "employee_number": x["employee_number"],
            "name": x["name"],
            "company_id": x["company_id"],
            "platform_driver_id": x["platform_driver_id"],
            "scheme": {"id": str(on[x["id"]].public_id), "name": on[x["id"]].name} if x["id"] in on else None,
        }
        for x in rows
    ]


def overview(db: Session, platform_id: int, **scope) -> dict:
    """The platform page's first tab: its drivers, how many have their ID on it, its schemes, the requests waiting."""
    from app.modules.payroll import platform_requests, schemes

    p = _platform(db, platform_id)
    rows = drivers(db, platform_id, **scope)
    offered = [s for s in schemes.list_schemes(db, platform_id=platform_id) if s["is_active"]]
    waiting = platform_requests.counts(db, **scope)["by_platform"].get(str(platform_id), 0)
    return {
        "platform": _out(p, people.platform_counts(db)),
        "drivers": len(rows),
        "with_driver_id": sum(1 for x in rows if x["platform_driver_id"]),
        "missing_driver_id": sum(1 for x in rows if not x["platform_driver_id"]),
        "schemes": len(offered),
        "by_scheme": {s["id"]: s["drivers"] for s in offered},
        "pending_requests": waiting,
    }


def set_driver_id(db: Session, platform_id: int, employee_public_id, *, value: str | None, actor_user_id: int,
                  **scope) -> dict:  # fmt: skip
    """His ID on his file (another driver's ID is refused here: moving an ID is the month's list), and this month's
    list with it."""
    from app.modules.payroll import rider_ids

    _platform(db, platform_id)
    e = people.set_platform_driver_id(
        db, employee_public_id, platform_id=platform_id, value=value, actor_user_id=actor_user_id, **scope
    )
    rider_ids.set_id(db, platform_id, today().replace(day=1), employee_public_id, value=value,
                     actor_user_id=actor_user_id, **scope)  # fmt: skip
    return next(x for x in drivers(db, platform_id, **scope) if x["id"] == str(e.public_id))
