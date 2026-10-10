"""A driver's month as the rule blocks read it, besides his approved daily reports and statement: the values of his
platform's monthly fields (entered in month review or imported: batch rows, marks, star day, lateness, tasks by type,
any number), the month totals of the platform's own daily fields, and the approved exceptions of his month (each with
its note and who approved it). The month review lists them per driver with what is missing or does not add up.

Nothing here changes once the company's payroll for the month is approved."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.daily_ops import service as daily_ops
from app.modules.identity import service as identity
from app.modules.payroll import forms
from app.modules.payroll.month_models import MonthException, MonthValue
from app.modules.payroll.rules.engine import Facts
from app.modules.payroll.rules.engine import MonthException as Excused
from app.modules.payroll.service import month_start
from app.modules.people import service as people

SIMPLE_BUILTINS = ("attendance_marks", "star_day_failed", "late_count", "absent_days")
CORRECTABLE = ("orders", "valid_days", "working_days", *SIMPLE_BUILTINS)


@dataclass
class Inputs:
    values: dict = field(default_factory=dict)  # monthly field -> value
    batches: list = field(default_factory=list)  # (batch, orders)
    tasks: dict | None = None  # task type -> count
    daily: dict = field(default_factory=dict)  # the platform's own daily fields: their month totals
    exceptions: list = field(default_factory=list)  # MonthException rows, live


def _locked(db: Session, company_id: int, month: date) -> None:
    from app.modules.payroll.service import month_locked

    if month_locked(db, company_id, month):
        raise AppError(409, "payroll_locked")


def load(db: Session, platforms: dict[int, int | None], month: date) -> dict[int, Inputs]:
    """Each driver's month inputs (`platforms`: driver -> his platform, whose fields count)."""
    month = month_start(month)
    out = {i: Inputs() for i in platforms}
    ids = list(platforms)
    if not ids:
        return out
    for v in db.scalars(select(MonthValue).where(MonthValue.employee_id.in_(ids), MonthValue.month == month)):
        if platforms.get(v.employee_id) != v.platform_id:
            continue  # a platform he left: its fields are not his any more
        row = out[v.employee_id]
        if v.key == "batch_orders":
            row.batches.append((int(v.sub), int(v.value)))
        elif v.key == "task_counts":
            row.tasks = (row.tasks or {}) | {v.sub: int(v.value)}
        else:
            row.values[v.key] = v.value
    for row in out.values():
        row.batches.sort()
    q = select(MonthException).where(
        MonthException.employee_id.in_(ids), MonthException.month == month, MonthException.cancelled_at.is_(None)
    )
    for e in db.scalars(q.order_by(MonthException.id)):
        out[e.employee_id].exceptions.append(e)
    from app.modules.payroll.statements import month_end

    extras = daily_ops.month_extras(db, ids, month, month_end(month))
    items: dict[int, list] = {}
    for i in ids:
        pid = platforms[i]
        if pid not in items:
            items[pid] = [x for x in (forms.daily_items(db, pid) or []) if not x.get("builtin")]
        if items[pid] and extras[i]:
            out[i].daily = forms.month_totals(items[pid], extras[i])
        elif items[pid]:
            out[i].daily = forms.month_totals(items[pid], [])
    return out


def facts(
    inputs: Inputs,
    *,
    orders,
    valid_days,
    working_days,
    hours,
    statement,
    system: dict,
    basic_salary,
    personal_rate,
) -> Facts:
    """What the blocks read: the month's figures as the run settled them, the monthly fields (over the statement's own
    figures), the daily fields' totals, his contract and his approved exceptions."""
    v = inputs.values

    def pick(key, fallback):
        return v[key] if key in v else fallback

    marks = pick("attendance_marks", statement.attendance_marks if statement else None)
    star = pick("star_day_failed", statement.star_day_failed if statement else None)
    late = pick("late_count", None)
    absent = pick("absent_days", system.get("absence_days"))
    custom = {k: x for k, x in v.items() if k not in SIMPLE_BUILTINS}
    return Facts(
        orders=orders,
        valid_days=valid_days,
        working_days=working_days,
        hours=hours,
        star_day_failed=None if star is None else bool(star),
        attendance_marks=None if marks is None else int(marks),
        late_count=None if late is None else int(late),
        absent_days=None if absent is None else int(absent),
        batches=tuple(inputs.batches) or None,
        batch_level=statement.batch_level if statement else None,
        tasks=inputs.tasks,
        basic_salary=basic_salary,
        personal_rate=personal_rate,
        fields={**inputs.daily, **custom},
        exceptions=tuple(Excused(e.kind, e.days, dict(e.corrections or {})) for e in inputs.exceptions),
    )


# ------------------------------------------------------------------ the office enters a driver's month


def _number(kind: str, raw) -> Decimal:
    if kind == "bool":
        if not isinstance(raw, bool):
            raise ValueError
        return Decimal(int(raw))
    if isinstance(raw, bool):
        raise ValueError
    d = Decimal(str(raw))
    if d < 0 or d >= Decimal("1000000") or d != d.quantize(Decimal("0.001")):
        raise ValueError
    if kind == "int" and d != d.to_integral_value():
        raise ValueError
    return d


def monthly_kinds(db: Session, platform_id: int) -> dict[str, str]:
    """The monthly fields the office may set for a platform's driver: the platform's own, and the built-in ones a
    scheme may read even when the platform did not list them."""
    kinds = {k: t for k, t in forms.MONTHLY_BUILTINS.items()}
    for it in forms.get(db, platform_id)["monthly"]:
        kinds[it["key"]] = it["type"]
    return kinds


def _driver(db: Session, public_id, **scope) -> people.EmployeeRef:
    e = people.ref_by_public_id(db, public_id, **scope)
    if not e.is_driver or not e.platform_id:
        raise AppError(422, "driver_no_platform")
    return e


def set_values(db: Session, public_id, *, month: date, data: dict, actor_user_id: int, **scope) -> dict:
    """The driver's month as the office corrects it: each value sent replaces his (an empty one clears it); batch rows
    and task counts, when sent, replace all of his for the month."""
    e = _driver(db, public_id, **scope)
    month = month_start(month)
    _locked(db, e.company_id, month)
    kinds = monthly_kinds(db, e.platform_id)
    rows: list[tuple[str, str, Decimal | None]] = []
    try:
        for key, raw in (data.get("values") or {}).items():
            kind = kinds.get(key)
            if kind is None or kind in ("batch_orders", "task_counts", "choice"):
                raise AppError(422, "field_unknown", field=key)
            rows.append((key, "", None if raw is None or raw == "" else _number(kind, raw)))
    except (ValueError, InvalidOperation, TypeError):
        raise AppError(422, "field_invalid", field=key) from None
    batches, tasks = data.get("batches"), data.get("tasks")
    before = {k: str(x.value) for k, x in _existing(db, e, month).items()}
    for key, sub, value in rows:
        _put(db, e, month, key, sub, value, source="manual", actor_user_id=actor_user_id)
    if batches is not None:
        seen = set()
        for b in batches:
            if b["batch"] in seen:
                raise AppError(422, "batch_duplicate", batch=b["batch"])
            seen.add(b["batch"])
        _replace(db, e, month, "batch_orders", {str(b["batch"]): Decimal(b["orders"]) for b in batches}, actor_user_id)
    if tasks is not None:
        allowed = {o["value"] for it in forms.get(db, e.platform_id)["monthly"] for o in it.get("options") or []}
        unknown = sorted(set(tasks) - allowed)
        if unknown:
            raise AppError(422, "field_unknown", field=unknown[0])
        _replace(db, e, month, "task_counts", {k: Decimal(int(n)) for k, n in tasks.items()}, actor_user_id)
    db.flush()
    after = {k: str(x.value) for k, x in _existing(db, e, month).items()}
    audit.record(
        db,
        action="payroll.month_values_set",
        entity_type="employee",
        entity_id=e.public_id,
        actor_user_id=actor_user_id,
        company_id=e.company_id,
        before={"month": month.isoformat(), **before},
        after={"month": month.isoformat(), **after},
    )
    db.commit()
    return driver_month(db, e, month)


def _existing(db: Session, e: people.EmployeeRef, month: date) -> dict[str, MonthValue]:
    q = select(MonthValue).where(
        MonthValue.employee_id == e.id, MonthValue.month == month, MonthValue.platform_id == e.platform_id
    )
    return {(f"{v.key}:{v.sub}" if v.sub else v.key): v for v in db.scalars(q)}


def _put(db, e, month, key, sub, value, *, source, actor_user_id, import_id=None) -> None:
    row = db.scalar(
        select(MonthValue).where(
            MonthValue.platform_id == e.platform_id,
            MonthValue.month == month,
            MonthValue.employee_id == e.id,
            MonthValue.key == key,
            MonthValue.sub == sub,
        )
    )
    if value is None:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        row = MonthValue(
            employee_id=e.id, company_id=e.company_id, platform_id=e.platform_id, month=month, key=key, sub=sub
        )
        db.add(row)
    row.value, row.source, row.import_id = value, source, import_id
    row.set_by, row.set_at = actor_user_id, utcnow()


def _replace(db, e, month, key, values: dict, actor_user_id, *, source="manual", import_id=None) -> None:
    db.execute(
        delete(MonthValue).where(
            MonthValue.platform_id == e.platform_id,
            MonthValue.month == month,
            MonthValue.employee_id == e.id,
            MonthValue.key == key,
        )
    )
    for sub, value in values.items():
        db.add(
            MonthValue(
                employee_id=e.id,
                company_id=e.company_id,
                platform_id=e.platform_id,
                month=month,
                key=key,
                sub=sub,
                value=value,
                source=source,
                import_id=import_id,
                set_by=actor_user_id,
            )
        )


def driver_month(db: Session, e: people.EmployeeRef, month: date) -> dict:
    found = load(db, {e.id: e.platform_id}, month)[e.id]
    return _inputs_out(db, found)


def _inputs_out(db: Session, found: Inputs, users: dict | None = None) -> dict:
    users = users if users is not None else identity.user_names(db, {x.approved_by for x in found.exceptions})
    return {
        "values": {k: str(v) for k, v in found.values.items()},
        "batches": [{"batch": b, "orders": n} for b, n in found.batches],
        "tasks": found.tasks or {},
        "daily": {k: str(v) for k, v in found.daily.items()},
        "exceptions": [_exception_out(x, users) for x in found.exceptions],
    }


# ------------------------------------------------------------------ exceptions


def _exception_out(x: MonthException, users: dict) -> dict:
    return {
        "id": str(x.public_id),
        "kind": x.kind,
        "days": x.days,
        "corrections": x.corrections,
        "note": x.note,
        "approved_by": users.get(x.approved_by),
        "created_at": x.created_at,
    }


def add_exception(db: Session, public_id, *, month: date, data: dict, actor_user_id: int, **scope) -> dict:
    """An exception the office approves for the driver's month, with its note: an accepted excuse, a day approved as an
    exception (how many days), or a company data error with the corrected figures."""
    e = _driver(db, public_id, **scope)
    month = month_start(month)
    _locked(db, e.company_id, month)
    corrections = dict(data.get("corrections") or {})
    if data["kind"] == "company_error":
        if not corrections:
            raise AppError(422, "field_required", field="corrections")
        kinds = monthly_kinds(db, e.platform_id) | {k: "int" for k in ("orders", "valid_days", "working_days")}
        for k, raw in corrections.items():
            kind = kinds.get(k)
            if k not in CORRECTABLE and (kind is None or kind not in ("int", "money", "bool")):
                raise AppError(422, "field_unknown", field=k)
            try:
                value = _number(kind or "int", raw)
            except (ValueError, InvalidOperation, TypeError):
                raise AppError(422, "field_invalid", field=k) from None
            corrections[k] = bool(value) if kind == "bool" else (int(value) if kind == "int" else str(value))
    elif corrections:
        raise AppError(422, "field_invalid", field="corrections")
    x = MonthException(
        employee_id=e.id,
        company_id=e.company_id,
        month=month,
        kind=data["kind"],
        days=data.get("days") or 0,
        corrections=corrections,
        note=data["note"],
        approved_by=actor_user_id,
    )
    db.add(x)
    db.flush()
    db.refresh(x)
    audit.record(
        db,
        action="payroll.exception_approved",
        entity_type="employee",
        entity_id=e.public_id,
        actor_user_id=actor_user_id,
        company_id=e.company_id,
        after={"month": month.isoformat(), "kind": x.kind, "days": x.days, "corrections": corrections, "note": x.note},
    )
    db.commit()
    return _exception_out(x, identity.user_names(db, {actor_user_id}))


def cancel_exception(db: Session, public_id, *, note: str, actor_user_id: int, all_companies: bool, company_ids):
    x = db.scalar(select(MonthException).where(MonthException.public_id == public_id).with_for_update())
    if x is None or not (all_companies or x.company_id in set(company_ids)):
        raise AppError(404, "exception_not_found")
    if x.cancelled_at is not None:
        raise AppError(409, "exception_cancelled")
    _locked(db, x.company_id, x.month)
    x.cancelled_by, x.cancelled_at, x.cancel_note = actor_user_id, utcnow(), note
    audit.record(
        db,
        action="payroll.exception_cancelled",
        entity_type="employee",
        entity_id=x.public_id,
        actor_user_id=actor_user_id,
        company_id=x.company_id,
        after={"month": x.month.isoformat(), "kind": x.kind, "note": note},
    )
    db.commit()
    return {"id": str(x.public_id), "cancelled": True}


# ------------------------------------------------------------------ the month review


def _ids_with_values(db: Session, platform_id: int, month: date) -> set[int]:
    q = select(MonthValue.employee_id).where(MonthValue.platform_id == platform_id, MonthValue.month == month)
    return set(db.scalars(q.distinct()))


def review(db: Session, *, platform_id: int, month: date, needs=None, all_companies: bool, company_ids) -> dict:
    """The platform's drivers for the month: their figures, the monthly fields, the totals of the daily ones, their
    exceptions, and the problems to settle before the run (a value missing, batch orders that do not add up to the
    approved daily orders, a daily report waiting, no scheme, no platform driver ID). `needs`: per driver, the
    figures his scheme reads that are missing (from the run engine)."""
    from app.modules.payroll import schemes, statements

    month = month_start(month)
    form = forms.get(db, platform_id)
    profiles = people.platform_profiles(
        db,
        platform_id,
        all_companies=all_companies,
        company_ids=company_ids,
        employee_ids=_ids_with_values(db, platform_id, month),
    )
    profiles = [p for p in profiles if p["platform_id"] == platform_id]
    ids = [p["id"] for p in profiles]
    found = load(db, {p["id"]: platform_id for p in profiles}, month)
    system = statements.system_counts(db, ids, month)
    sts = statements.for_month(db, ids, month)
    assigned = schemes.for_month(db, ids, month)
    has_schemes = platform_id in schemes.platforms_with_schemes(db)
    locked = statements.locked_months(db, {(p["company_id"], month) for p in profiles})
    users = identity.user_names(db, {x.approved_by for f in found.values() for x in f.exceptions})
    required = [x["key"] for x in form["monthly"] if x["required"]]
    missing_of = needs or (lambda _p, _f: [])
    rows, problems = [], defaultdict(int)
    for p in profiles:
        f, sy, st = found[p["id"]], system[p["id"]], sts.get(p["id"])
        approved = st if st is not None and st.status == "approved" else None
        orders = approved.orders if approved and approved.orders is not None else sy["orders"]
        valid = approved.valid_days if approved and approved.valid_days is not None else sy["valid_days"]
        issues = []
        lacking = [k for k in required if not _has(f, k)]
        lacking += [k for k in missing_of(p, f) if k not in lacking]
        if lacking:
            issues.append("values_missing")
        if f.batches and sum(n for _, n in f.batches) != orders and orders:
            issues.append("orders_conflict")  # the partner's batch rows and the approved daily orders differ
        if sy["pending_reports"]:
            issues.append("daily_pending")
        scheme = assigned.get(p["id"])
        if has_schemes and scheme is None:
            issues.append("scheme_missing")
        if not p["platform_driver_id"]:
            issues.append("driver_id_missing")
        for i in issues:
            problems[i] += 1
        rows.append(
            {
                "employee": {"id": p["public_id"], "name": p["name"], "number": p["employee_number"]},
                "company_id": p["company_id"],
                "platform_driver_id": p["platform_driver_id"],
                "scheme": {"id": str(scheme.public_id), "name": scheme.name} if scheme else None,
                "orders": orders,
                "valid_days": valid,
                "working_days": sy["working_days"],
                "pending_reports": sy["pending_reports"],
                **_inputs_out(db, f, users),
                "missing": lacking,
                "problems": issues,
                "locked": (p["company_id"], month) in locked,
            }
        )
    return {
        "month": month,
        "platform_id": platform_id,
        "form": form,
        "rows": rows,
        "problems": dict(problems),
        "drivers": len(rows),
    }


def _has(f: Inputs, key: str) -> bool:
    if key == "batch_orders":
        return bool(f.batches)
    if key == "task_counts":
        return f.tasks is not None
    return key in f.values or key in f.daily
