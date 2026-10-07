"""Work violations (BRD 5.9 FR-VIO-01..05, BR-09, BR-10, BR-13, UAT-05; TRK-M-02, TRK-M-03).

A violation names a driver, a type (each type belongs to one of the six sources: attendance, cash, orders,
complaints, accidents, tracking) and when it happened. It comes from the office (an order or a complaint, with its
reference), from an alert a supervisor turns into one (speed and the like are alerts until then, BR-13), or from the
system itself: a fake location (TRK-M-02) and the third signal loss in a week (TRK-M-03).

Its course (FR-VIO-02): pending review; then approved, with a penalty or as a warning, or excluded with the reason;
an approved one may be objected to by the driver from the app until its deadline (BR-09, 48 hours by default); the
objection is decided once more, upheld or overturned, and that is final. A cause outside the driver's responsibility
from the client's list (BR-10) excludes it as it is recorded (UAT-05: an order the customer cancelled is no violation).
A penalty becomes a payroll deduction only once final: when the deadline passes without an objection, or when the
objection is upheld.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import business_date, today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.payroll import service as payroll
from app.modules.people import service as people
from app.modules.violations.models import Cause, SignalLoss, Type, Violation

SOURCES = ("attendance", "cash", "orders", "complaints", "accidents", "tracking")
CLOCK_SKEW = timedelta(minutes=5)
OLDEST = timedelta(days=90)
ERRORS = {"types_code_key": "violation_type_exists", "causes_code_key": "violation_cause_exists"}
SEEN_BY_DRIVER = ("approved", "objected", "upheld", "overturned")


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Violation.company_id.in_(list(company_ids)))


def _get(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Violation:
    q = _scoped(select(Violation).where(Violation.public_id == public_id), all_companies, company_ids)
    v = db.scalar(q.with_for_update() if lock else q)
    if v is None:
        raise AppError(404, "violation_not_found")
    return v


def _final(v: Violation, now: datetime) -> bool:
    return v.status in ("excluded", "upheld", "overturned") or (
        v.status == "approved" and v.objection_deadline is not None and v.objection_deadline <= now
    )


def _type_out(t: Type) -> dict:
    return {
        "id": t.id,
        "code": t.code,
        "name": t.name,
        "source": t.source,
        "amount": t.amount,
        "active": t.active,
        "version": t.version,
    }


def _cause_out(c: Cause) -> dict:
    return {"id": c.id, "code": c.code, "name": c.name, "active": c.active, "version": c.version}


def _out(db: Session, rows: list[Violation]) -> list[dict]:
    names = people.names(db, {v.employee_id for v in rows})
    plates = fleet.plate_numbers(db, {v.vehicle_id for v in rows if v.vehicle_id})
    types = {t.id: t for t in db.scalars(select(Type).where(Type.id.in_({v.type_id for v in rows})))}
    causes = {c.id: c for c in db.scalars(select(Cause).where(Cause.id.in_({v.cause_id for v in rows if v.cause_id})))}
    users = identity.user_names(
        db, {u for v in rows for u in (v.reviewed_by, v.final_by, v.created_by) if u is not None}
    )
    now = utcnow()
    out = []
    for v in rows:
        t, c = types[v.type_id], causes.get(v.cause_id)
        out.append(
            {
                "id": str(v.public_id),
                "number": v.number,
                "company_id": v.company_id,
                "driver": names.get(v.employee_id),
                "type": {"id": t.id, "code": t.code, "name": t.name, "source": t.source},
                "cause": None if c is None else {"id": c.id, "code": c.code, "name": c.name},
                "vehicle_plate": plates.get(v.vehicle_id),
                "occurred_at": v.occurred_at,
                "business_date": v.business_date,
                "description": v.description,
                "reference": v.reference,
                "evidence_sha256": v.evidence_sha256,
                "origin": v.origin,
                "status": v.status,
                "final": _final(v, now),
                "amount": v.amount,
                "review_note": v.review_note,
                "reviewed_by": users.get(v.reviewed_by),
                "reviewed_at": v.reviewed_at,
                "objection_deadline": v.objection_deadline,
                "objection": v.objection,
                "objection_sha256": v.objection_sha256,
                "objected_at": v.objected_at,
                "final_note": v.final_note,
                "final_by": users.get(v.final_by),
                "final_at": v.final_at,
                "deduction": payroll.deduction(db, v.deduction_id),
                "created_by": users.get(v.created_by),
                "created_at": v.created_at,
                "version": v.version,
            }
        )
    return out


def _audit(db: Session, action: str, v: Violation, *, actor_user_id: int | None, after: dict | None = None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="violation",
        entity_id=v.public_id,
        actor_user_id=actor_user_id,
        company_id=v.company_id,
        after={"number": v.number, "status": v.status, "amount": v.amount} | (after or {}),
    )


def _flush(db: Session, row) -> None:
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        code = ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None


# ------------------------------------------------------------------ types and causes (the client's lists)


def list_types(db: Session) -> list[dict]:
    return [_type_out(t) for t in db.scalars(select(Type).order_by(Type.source, Type.id))]


def save_type(db: Session, data: dict, *, type_id: int | None = None, actor_user_id: int) -> dict:
    if type_id is None:
        t = Type(code=data["code"], name=data["name"], source=data["source"], amount=data.get("amount"))
        _flush(db, t)
    else:
        t = db.scalar(select(Type).where(Type.id == type_id).with_for_update())
        if t is None:
            raise AppError(404, "violation_type_not_found")
        if data.get("version") != t.version:
            raise AppError(409, "version_conflict")
        # the code and the source stay: records and the system's own violations name them
        t.name, t.amount, t.active = data["name"], data.get("amount"), data.get("active", True)
        t.version += 1
    audit.record(
        db,
        action="violation_type.saved",
        entity_type="violation_type",
        entity_id=t.code,
        actor_user_id=actor_user_id,
        after={"name": t.name, "amount": t.amount, "active": t.active},
    )
    db.commit()
    return _type_out(t)


def list_causes(db: Session) -> list[dict]:
    return [_cause_out(c) for c in db.scalars(select(Cause).order_by(Cause.id))]


def save_cause(db: Session, data: dict, *, cause_id: int | None = None, actor_user_id: int) -> dict:
    if cause_id is None:
        c = Cause(code=data["code"], name=data["name"])
        _flush(db, c)
    else:
        c = db.scalar(select(Cause).where(Cause.id == cause_id).with_for_update())
        if c is None:
            raise AppError(404, "violation_cause_not_found")
        if data.get("version") != c.version:
            raise AppError(409, "version_conflict")
        c.name, c.active = data["name"], data.get("active", True)
        c.version += 1
    audit.record(
        db,
        action="violation_cause.saved",
        entity_type="violation_cause",
        entity_id=c.code,
        actor_user_id=actor_user_id,
        after={"name": c.name, "active": c.active},
    )
    db.commit()
    return _cause_out(c)


# ------------------------------------------------------------------ recording


def _record(
    db: Session,
    *,
    employee: people.EmployeeRef,
    vtype: Type,
    occurred_at: datetime,
    description: str,
    origin: str,
    reference: str | None = None,
    cause: Cause | None = None,
    vehicle_id: int | None = None,
    evidence: str | None = None,
    alert_id: int | None = None,
    auto_key: str | None = None,
    created_by: int | None = None,
) -> Violation | None:
    """The violation, pending review; excluded at once when its cause is on the client's list. None when the system
    already opened this one (its auto key)."""
    if vehicle_id is None:  # the vehicle he held then, if any
        held = fleet.custodies_for_driver(db, employee.id, occurred_at, occurred_at)[-1:]
        vehicle_id = held[0].vehicle_id if held else None
    excluded = cause is not None and cause.active
    v = Violation(
        company_id=employee.company_id,
        employee_id=employee.id,
        type_id=vtype.id,
        cause_id=cause.id if cause else None,
        vehicle_id=vehicle_id,
        occurred_at=occurred_at,
        business_date=business_date(occurred_at),
        description=description,
        reference=reference,
        evidence_sha256=evidence,
        origin=origin,
        alert_id=alert_id,
        auto_key=auto_key,
        status="excluded" if excluded else "pending",
        reviewed_at=utcnow() if excluded else None,
        created_by=created_by,
    )
    try:
        with db.begin_nested():  # added inside: a conflict takes it out of the session again
            db.add(v)
            db.flush()
    except IntegrityError as exc:
        if auto_key is not None and violated_constraint(exc) == "violations_auto_key_idx":
            return None
        raise
    db.refresh(v)
    if excluded:
        _audit(db, "violation.excluded", v, actor_user_id=created_by, after={"cause": cause.code, "auto": True})
    else:
        notifications.raise_alert(
            db,
            "violation_review",
            company_id=v.company_id,
            entity_type="violation",
            entity_id=v.public_id,
            params={"number": v.number, "driver": employee.name, "type": vtype.name},
            dedupe_key=f"violation_review:{v.id}",
        )
        _audit(db, "violation.recorded", v, actor_user_id=created_by, after={"type": vtype.code, "origin": origin})
    emit(
        db,
        "violation.recorded",
        v.public_id,
        {"violation_id": str(v.public_id), "number": v.number, "type": vtype.code, "status": v.status},
    )
    return v


def create(db: Session, data: dict, *, actor_user_id: int, permissions: Iterable[str], **scope) -> dict:
    """By the office (FR-VIO-01): an order, a complaint, an absence... or an alert turned into a violation (BR-13)."""
    employee = people.ref_by_public_id(db, data["employee_id"], **scope)
    vtype = db.get(Type, data["type_id"])
    if vtype is None or not vtype.active:
        raise AppError(422, "violation_type_not_found")
    cause = None
    if data.get("cause_id") is not None:
        cause = db.get(Cause, data["cause_id"])
        if cause is None:
            raise AppError(422, "violation_cause_not_found")
    at: datetime = data["occurred_at"]
    now = utcnow()
    if at > now + CLOCK_SKEW:
        raise AppError(422, "time_in_future")
    if at < now - OLDEST:
        raise AppError(422, "time_too_old")
    if data.get("evidence_sha256"):
        files.get(db, data["evidence_sha256"])
    alert_id = None
    if data.get("alert_id"):  # the alert is handled by becoming a violation
        alert_id = notifications.take_alert(
            db, data["alert_id"], actor_user_id=actor_user_id, permissions=permissions, **scope
        )
    v = _record(
        db,
        employee=employee,
        vtype=vtype,
        occurred_at=at,
        description=data["description"],
        origin="alert" if alert_id else "office",
        reference=data.get("reference"),
        cause=cause,
        evidence=data.get("evidence_sha256"),
        alert_id=alert_id,
        created_by=actor_user_id,
    )
    db.commit()
    return _out(db, [v])[0]


def _system(db: Session, code: str, *, employee_id: int, occurred_at: datetime, auto_key: str, **params):
    """Opened by the system, described in the default language."""
    vtype = db.scalar(select(Type).where(Type.code == code))
    employee = people.ref(db, employee_id)
    if vtype is None or not vtype.active or employee is None:
        return None  # the client switched this type off
    return _record(
        db,
        employee=employee,
        vtype=vtype,
        occurred_at=occurred_at,
        description=i18n.t(db, i18n.default_language(db).code, f"violation_text.{code}", **params),
        origin="system",
        auto_key=auto_key,
    )


def fake_location(db: Session, *, employee_id: int, device_id: int, at: datetime) -> None:
    """TRK-M-02: points from a location-faking app were refused; the attempt waits for review, once a day."""
    _system(
        db,
        "mock_location",
        employee_id=employee_id,
        occurred_at=at,
        auto_key=f"mock:{device_id}:{business_date(at)}",
    )


def signal_lost(db: Session, *, employee_id: int, custody_id: int, lost_at: datetime) -> None:
    """TRK-M-03: each signal loss is kept; the configured number within the configured days (3 in 7 by default)
    opens a violation for review, and the count starts again after it."""
    try:
        with db.begin_nested():
            db.add(SignalLoss(employee_id=employee_id, custody_id=custody_id, lost_at=lost_at))
            db.flush()
    except IntegrityError:
        return  # this silence was already counted
    s = org.get_section(db, "violations")
    if not s.signal_loss_count:
        return
    since = lost_at - timedelta(days=s.signal_loss_days)
    last = db.scalar(
        select(func.max(Violation.occurred_at))
        .join(Type, Type.id == Violation.type_id)
        .where(Violation.employee_id == employee_id, Type.code == "signal_loss")
    )
    if last is not None and last > since:
        since = last
    n = db.scalar(
        select(func.count())
        .select_from(SignalLoss)
        .where(SignalLoss.employee_id == employee_id, SignalLoss.lost_at > since, SignalLoss.lost_at <= lost_at)
    )
    if n >= s.signal_loss_count:
        _system(
            db,
            "signal_loss",
            employee_id=employee_id,
            occurred_at=lost_at,
            auto_key=f"signal:{employee_id}:{lost_at.isoformat()}",
            count=n,
            days=s.signal_loss_days,
        )


# ------------------------------------------------------------------ reviewing (FR-VIO-02)


def _pending(v: Violation) -> None:
    if v.status != "pending":
        raise AppError(409, "violation_not_pending", status=v.status)


def approve(db: Session, public_id, *, amount, note: str | None, actor_user_id: int, **scope) -> dict:
    """Approved, with a penalty (the type's by default) or as a warning (zero): the driver is told, and may object
    until the deadline."""
    v = _get(db, public_id, lock=True, **scope)
    _pending(v)
    vtype = db.get(Type, v.type_id)
    hours = org.get_section(db, "violations").objection_hours
    now = utcnow()
    v.amount = amount if amount is not None else vtype.amount
    v.status, v.review_note, v.reviewed_by, v.reviewed_at = "approved", note, actor_user_id, now
    v.objection_deadline = now + timedelta(hours=hours)
    v.version += 1
    notifications.resolve(db, f"violation_review:{v.id}")
    notifications.notify_driver(
        db,
        v.employee_id,
        "violation_approved",
        params={
            "number": v.number,
            "type": vtype.name,
            "amount": f"{v.amount or 0:.3f}",
            "hours": hours,
        },
        entity_type="violation",
        entity_id=v.public_id,
    )
    _audit(db, "violation.approved", v, actor_user_id=actor_user_id, after={"note": note, "hours": hours})
    if hours == 0:  # no objection allowed: final at once
        _deduct(db, v, actor_user_id)
    db.commit()
    return _out(db, [v])[0]


def exclude(db: Session, public_id, *, note: str, actor_user_id: int, **scope) -> dict:
    v = _get(db, public_id, lock=True, **scope)
    _pending(v)
    v.status, v.review_note, v.reviewed_by, v.reviewed_at = "excluded", note, actor_user_id, utcnow()
    v.version += 1
    notifications.resolve(db, f"violation_review:{v.id}")
    _audit(db, "violation.excluded", v, actor_user_id=actor_user_id, after={"note": note})
    db.commit()
    return _out(db, [v])[0]


def decide_objection(db: Session, public_id, *, uphold: bool, note: str, actor_user_id: int, **scope) -> dict:
    """The final decision on the driver's objection: upheld (the penalty stands and is deducted) or overturned."""
    v = _get(db, public_id, lock=True, **scope)
    if v.status != "objected":
        raise AppError(409, "violation_not_objected", status=v.status)
    v.status = "upheld" if uphold else "overturned"
    v.final_note, v.final_by, v.final_at = note, actor_user_id, utcnow()
    v.version += 1
    notifications.resolve(db, f"violation_objected:{v.id}")
    notifications.notify_driver(
        db,
        v.employee_id,
        "violation_upheld" if uphold else "violation_overturned",
        params={"number": v.number, "reason": note},
        entity_type="violation",
        entity_id=v.public_id,
    )
    _audit(db, f"violation.{v.status}", v, actor_user_id=actor_user_id, after={"note": note})
    if uphold:
        _deduct(db, v, actor_user_id)
    db.commit()
    return _out(db, [v])[0]


def _deduct(db: Session, v: Violation, actor_user_id: int) -> None:
    """A final penalty: one approved deduction from this month's payroll (the monthly cap and the carrying forward
    apply as to any deduction)."""
    if not v.amount or v.deduction_id is not None:
        return
    vtype = db.get(Type, v.type_id)
    v.deduction_id = payroll.create_deduction(
        db,
        employee_id=v.employee_id,
        company_id=v.company_id,
        source_type="violation",
        source_id=v.id,
        reason=f"#{v.number} {vtype.name.get('ar') or vtype.code}"[:200],
        total=v.amount,
        installments=1,
        start_month=payroll.month_start(today()),
        actor_user_id=actor_user_id,
    )


def finalize_due(db: Session) -> int:
    """Hourly: approved violations whose objection deadline passed without one are final; their penalty is
    deducted (by whoever approved it)."""
    rows = list(
        db.scalars(
            select(Violation)
            .where(
                Violation.status == "approved",
                Violation.deduction_id.is_(None),
                Violation.amount > 0,
                Violation.objection_deadline <= utcnow(),
            )
            .with_for_update(skip_locked=True)
        )
    )
    for v in rows:
        _deduct(db, v, v.reviewed_by)
        _audit(db, "violation.final", v, actor_user_id=None)
    db.commit()
    return len(rows)


# ------------------------------------------------------------------ the driver (FR-VIO-04)


def for_driver(db: Session, employee_id: int, *, limit: int = 50) -> list[dict]:
    rows = list(
        db.scalars(
            select(Violation)
            .where(Violation.employee_id == employee_id, Violation.status.in_(SEEN_BY_DRIVER))
            .order_by(Violation.occurred_at.desc(), Violation.id.desc())
            .limit(limit)
        )
    )
    types = {t.id: t for t in db.scalars(select(Type).where(Type.id.in_({v.type_id for v in rows})))}
    now = utcnow()
    return [
        {
            "id": str(v.public_id),
            "number": v.number,
            "type_name": types[v.type_id].name,
            "occurred_at": v.occurred_at,
            "description": v.description if v.origin != "system" else None,
            "reference": v.reference,
            "amount": v.amount,
            "status": v.status,
            "objection_deadline": v.objection_deadline,
            "can_object": v.status == "approved" and v.objection_deadline is not None and now < v.objection_deadline,
            "objection": v.objection,
            "final_note": v.final_note,
        }
        for v in rows
    ]


def object_to(db: Session, employee_id: int, public_id, *, text: str, file_sha256: str | None, device_id: int) -> dict:
    v = db.scalar(
        select(Violation)
        .where(Violation.public_id == public_id, Violation.employee_id == employee_id)
        .with_for_update()
    )
    if v is None or v.status not in SEEN_BY_DRIVER:
        raise AppError(404, "violation_not_found")
    if v.status != "approved":  # a retry finds the objection it sent
        raise AppError(409, "objection_exists" if v.objected_at else "violation_not_objectable")
    if v.objection_deadline is None or utcnow() >= v.objection_deadline:
        raise AppError(409, "objection_too_late")
    if file_sha256 and files.get(db, file_sha256).uploaded_by_device != device_id:
        raise AppError(422, "file_not_found")  # his own file, from this phone
    v.status, v.objection, v.objection_sha256, v.objected_at = "objected", text, file_sha256, utcnow()
    v.version += 1
    employee = people.ref(db, employee_id)
    notifications.raise_alert(
        db,
        "violation_objected",
        company_id=v.company_id,
        entity_type="violation",
        entity_id=v.public_id,
        params={"number": v.number, "driver": employee.name},
        dedupe_key=f"violation_objected:{v.id}",
    )
    _audit(db, "violation.objected", v, actor_user_id=None, after={"objection": text})
    db.commit()
    return [x for x in for_driver(db, employee_id) if x["id"] == str(v.public_id)][0]


# ------------------------------------------------------------------ the office's lists


def list_violations(
    db: Session,
    *,
    status: str | None = None,
    source: str | None = None,
    driver_public_id=None,
    date_from=None,
    date_to=None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Violation), **scope)
    if status:
        q = q.where(Violation.status.in_(status.split(",")))
    if source:
        q = q.where(Violation.type_id.in_(select(Type.id).where(Type.source == source)))
    if driver_public_id:
        q = q.where(Violation.employee_id == people.ref_by_public_id(db, driver_public_id, **scope).id)
    if date_from:
        q = q.where(Violation.business_date >= date_from)
    if date_to:
        q = q.where(Violation.business_date <= date_to)
    rows = db.scalars(q.order_by(Violation.occurred_at.desc(), Violation.id.desc()).limit(limit).offset(offset))
    return _out(db, list(rows))


def get(db: Session, public_id, **scope) -> dict:
    return _out(db, [_get(db, public_id, **scope)])[0]


def violation_file(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    v = _get(db, public_id, **scope)
    if sha256 not in (v.evidence_sha256, v.objection_sha256):
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def counts(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> dict:
    q = _scoped(select(Violation.status, func.count()).group_by(Violation.status), all_companies, company_ids)
    by = dict(db.execute(q.where(Violation.status.in_(("pending", "objected")))).all())
    return {"pending": by.get("pending", 0), "objected": by.get("objected", 0)}
