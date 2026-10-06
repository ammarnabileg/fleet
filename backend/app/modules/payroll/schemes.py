"""Pay schemes as data (docs/payroll-schemes.md): what each platform offers, who is on which scheme month by month,
and the drivers' requests from the app to change it, decided in the dashboard.

- A scheme names its calculator (calculators.py) and holds its numbers; its prices never change once a driver is on
  it (a new price is a new scheme, and the drivers move to it from a month), so a month is never recomputed on a
  price it did not have.
- A driver's scheme runs from the first of a month; assigning from a month replaces what was set from it on. A month
  whose payroll is approved (or any later one) is never reassigned.
- A request from the app is for the next month, one open request per driver; approving it moves the driver from the
  first month that has no approved payroll yet.
"""

import logging
from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import messaging
from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.integrations import service as integrations
from app.modules.payroll.calculators import Rules, Step
from app.modules.payroll.models import DriverScheme, Platform, Run, Scheme, SchemeChangeRequest, SchemeStep
from app.modules.payroll.service import add_months, month_start
from app.modules.people import service as people

log = logging.getLogger(__name__)

STEP_KINDS = {
    "platform_rates": set(),
    "per_order": set(),
    "batch": {"batch_rate"},
    "tiered_target": {"tier_bonus", "marks_deduction", "marks_reduce"},
}
PRICES = (  # what a driver is paid on: fixed once a driver is on the scheme
    "calculator",
    "per_order",
    "target_orders",
    "required_valid_days",
    "missing_order_rate",
    "reduced_rate",
    "bonus_when_reduced",
    "marks_when_reduced",
    "floor_at_zero",
    "company_covers",
)
TERMS = ("name", "description", "is_active", "driver_selectable")


# ------------------------------------------------------------------ schemes


def _steps(db: Session, scheme_ids) -> dict[int, list[SchemeStep]]:
    out: dict[int, list[SchemeStep]] = {i: [] for i in scheme_ids}
    if out:
        q = select(SchemeStep).where(SchemeStep.scheme_id.in_(list(out)))
        for s in db.scalars(q.order_by(SchemeStep.kind, SchemeStep.threshold)):
            out[s.scheme_id].append(s)
    return out


def _rules(s: Scheme, steps: list[SchemeStep]) -> Rules:
    by_kind: dict[str, list[Step]] = {}
    for st in sorted(steps, key=lambda x: x.threshold):
        by_kind.setdefault(st.kind, []).append(Step(st.threshold, st.amount))
    return Rules(
        calculator=s.calculator,
        per_order=s.per_order,
        target_orders=s.target_orders,
        missing_order_rate=s.missing_order_rate,
        reduced_rate=s.reduced_rate,
        bonus_when_reduced=s.bonus_when_reduced,
        marks_when_reduced=s.marks_when_reduced,
        floor_at_zero=s.floor_at_zero,
        steps=by_kind,
    )


def rules_for(db: Session, schemes: dict[int, Scheme]) -> dict[int, Rules]:
    steps = _steps(db, schemes)
    return {i: _rules(s, steps[i]) for i, s in schemes.items()}


def _counts(db: Session, month: date) -> dict[int, int]:
    q = (
        select(DriverScheme.scheme_id, func.count())
        .where(DriverScheme.valid_from <= month, or_(DriverScheme.valid_to.is_(None), DriverScheme.valid_to > month))
        .group_by(DriverScheme.scheme_id)
    )
    return dict(db.execute(q).all())


def _out(s: Scheme, steps: list[SchemeStep], counts: dict[int, int]) -> dict:
    return {
        "id": str(s.public_id),
        "platform_id": s.platform_id,
        "code": s.code,
        "name": s.name,
        "description": s.description,
        "calculator": s.calculator,
        "per_order": s.per_order,
        "target_orders": s.target_orders,
        "required_valid_days": s.required_valid_days,
        "missing_order_rate": s.missing_order_rate,
        "reduced_rate": s.reduced_rate,
        "bonus_when_reduced": s.bonus_when_reduced,
        "marks_when_reduced": s.marks_when_reduced,
        "floor_at_zero": s.floor_at_zero,
        "company_covers": list(s.company_covers),
        "driver_selectable": s.driver_selectable,
        "is_active": s.is_active,
        "steps": [{"kind": x.kind, "threshold": x.threshold, "amount": x.amount} for x in steps],
        "drivers": counts.get(s.id, 0),  # on it this month
        "version": s.version,
    }


def _many(db: Session, rows: list[Scheme]) -> list[dict]:
    steps = _steps(db, [s.id for s in rows])
    counts = _counts(db, month_start(today()))
    return [_out(s, steps[s.id], counts) for s in rows]


def list_schemes(db: Session, *, platform_id: int | None = None, offered_only: bool = False) -> list[dict]:
    q = select(Scheme).order_by(Scheme.platform_id, Scheme.is_active.desc(), Scheme.id)
    if platform_id is not None:
        q = q.where(Scheme.platform_id == platform_id)
    if offered_only:
        q = q.where(Scheme.is_active.is_(True), Scheme.driver_selectable.is_(True))
    return _many(db, list(db.scalars(q)))


def _by_public_id(db: Session, public_id, *, lock: bool = False) -> Scheme:
    q = select(Scheme).where(Scheme.public_id == public_id)
    s = db.scalar(q.with_for_update() if lock else q)
    if s is None:
        raise AppError(404, "scheme_not_found")
    return s


def get(db: Session, public_id) -> dict:
    return _many(db, [_by_public_id(db, public_id)])[0]


def _check(data: dict) -> None:
    calc = data["calculator"]
    if calc in ("per_order", "tiered_target") and data.get("per_order") is None:
        raise AppError(422, "field_required", field="per_order")
    if calc == "tiered_target" and data.get("reduced_rate") is None:
        raise AppError(422, "field_required", field="reduced_rate")
    steps = data.get("steps") or []
    seen = set()
    for st in steps:
        if st["kind"] not in STEP_KINDS[calc]:
            raise AppError(422, "scheme_step_invalid", kind=st["kind"])
        if (st["kind"] == "marks_reduce") != (st.get("amount") is None):
            raise AppError(422, "scheme_step_invalid", kind=st["kind"])
        key = (st["kind"], st["threshold"])
        if key in seen:
            raise AppError(422, "scheme_step_invalid", kind=st["kind"])
        seen.add(key)
    if calc == "batch" and not any(st["kind"] == "batch_rate" for st in steps):
        raise AppError(422, "field_required", field="steps")


def _used(db: Session, scheme_id: int) -> bool:
    return db.scalar(select(DriverScheme.id).where(DriverScheme.scheme_id == scheme_id).limit(1)) is not None


def create(db: Session, data: dict, *, actor_user_id: int) -> dict:
    if db.get(Platform, data["platform_id"]) is None:
        raise AppError(404, "platform_not_found")
    _check(data)
    data = dict(data)
    steps = data.pop("steps", []) or []
    data["name"] = i18n.validate_localized(db, data["name"])
    if data.get("description"):
        data["description"] = i18n.validate_localized(db, data["description"])
    s = Scheme(**data, created_by=actor_user_id)
    db.add(s)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "schemes_platform_id_key":
            raise
        raise AppError(409, "scheme_code_taken") from None
    for st in steps:
        db.add(SchemeStep(scheme_id=s.id, kind=st["kind"], threshold=st["threshold"], amount=st.get("amount")))
    db.flush()
    db.refresh(s)
    audit.record(
        db,
        action="scheme.created",
        entity_type="scheme",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        after={k: data.get(k) for k in ("platform_id", "code", *PRICES)} | {"steps": steps},
    )
    db.commit()
    return get(db, s.public_id)


def update(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int) -> dict:
    s = _by_public_id(db, public_id, lock=True)
    if s.version != version:
        raise AppError(409, "version_conflict")
    prices = {k: v for k, v in changes.items() if k in (*PRICES, "steps")}
    if prices and _used(db, s.id):
        raise AppError(409, "scheme_in_use")  # a new price is a new scheme: the months paid on this one stay as paid
    current = {k: getattr(s, k) for k in PRICES} | {
        "steps": [{"kind": x.kind, "threshold": x.threshold, "amount": x.amount} for x in _steps(db, [s.id])[s.id]]
    }
    _check(current | prices)
    if "name" in changes:
        changes["name"] = i18n.validate_localized(db, changes["name"])
    if changes.get("description"):
        changes["description"] = i18n.validate_localized(db, changes["description"])
    before = {k: current.get(k, getattr(s, k, None)) for k in changes}
    for k, v in changes.items():
        if k != "steps":
            setattr(s, k, v)
    if "steps" in changes:
        db.execute(delete(SchemeStep).where(SchemeStep.scheme_id == s.id))
        for st in changes["steps"]:
            db.add(SchemeStep(scheme_id=s.id, kind=st["kind"], threshold=st["threshold"], amount=st.get("amount")))
    s.version += 1
    db.flush()
    audit.record(
        db,
        action="scheme.updated",
        entity_type="scheme",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after=changes,
    )
    db.commit()
    return get(db, s.public_id)


# ------------------------------------------------------------------ who is on which scheme


def for_month(db: Session, employee_ids, month: date) -> dict[int, Scheme]:
    """Each driver's scheme in the month."""
    ids = list(employee_ids)
    if not ids:
        return {}
    q = (
        select(DriverScheme.employee_id, Scheme)
        .join(Scheme, Scheme.id == DriverScheme.scheme_id)
        .where(
            DriverScheme.employee_id.in_(ids),
            DriverScheme.valid_from <= month,
            or_(DriverScheme.valid_to.is_(None), DriverScheme.valid_to > month),
        )
    )
    return {e: s for e, s in db.execute(q)}


def platforms_with_schemes(db: Session) -> set[int]:
    return set(db.scalars(select(Scheme.platform_id).where(Scheme.is_active.is_(True)).distinct()))


def _locked_from(db: Session, company_id: int, month: date) -> bool:
    """A payroll approved for this month or a later one: reassigning would change what was paid."""
    q = select(Run.id).where(Run.company_id == company_id, Run.month >= month, Run.status != "draft").limit(1)
    return db.scalar(q) is not None


def assign(
    db: Session,
    employee: people.EmployeeRef,
    scheme: Scheme,
    month: date,
    *,
    source: str,
    actor_user_id: int | None,
    request: SchemeChangeRequest | None = None,
) -> None:
    """In the caller's transaction: the driver is on this scheme from the month on (what was set from it is
    replaced)."""
    if not employee.is_driver:
        raise AppError(422, "not_a_driver")
    if employee.platform_id != scheme.platform_id:
        raise AppError(422, "scheme_platform_mismatch")
    month = month_start(month)
    if _locked_from(db, employee.company_id, month):
        raise AppError(409, "payroll_locked")
    rows = db.scalars(select(DriverScheme).where(DriverScheme.employee_id == employee.id).with_for_update()).all()
    before = [(r.scheme_id, r.valid_from, r.valid_to) for r in rows]
    for r in rows:
        if r.valid_from >= month:
            db.delete(r)
        elif r.valid_to is None or r.valid_to > month:
            r.valid_to = month
    db.flush()
    db.add(
        DriverScheme(
            employee_id=employee.id,
            scheme_id=scheme.id,
            valid_from=month,
            source=source,
            request_id=request.id if request else None,
            set_by=actor_user_id,
        )
    )
    db.flush()
    audit.record(
        db,
        action="employee.scheme_set",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "device",
        company_id=employee.company_id,
        before={"schemes": [[str(s), str(f), str(t) if t else None] for s, f, t in before]},
        after={"scheme": str(scheme.public_id), "from": month.isoformat(), "source": source},
    )


def assign_many(db: Session, scheme_public_id, employee_ids, month: date, *, actor_user_id: int, **scope) -> dict:
    """The office moves drivers to a scheme from a month (a first assignment, or everyone to a new price)."""
    scheme = _by_public_id(db, scheme_public_id)
    if not scheme.is_active:
        raise AppError(409, "scheme_not_available")
    done, skipped = 0, []
    for public_id in employee_ids:
        employee = people.ref_by_public_id(db, public_id, **scope)
        try:
            with db.begin_nested():
                assign(db, employee, scheme, month, source="office", actor_user_id=actor_user_id)
            done += 1
        except AppError as exc:
            skipped.append({"employee": {"id": str(employee.public_id), "name": employee.name}, "code": exc.code})
    db.commit()
    return {"set": done, "skipped": skipped, "from": month_start(month)}


def history(db: Session, employee_id: int) -> list[dict]:
    q = (
        select(DriverScheme, Scheme)
        .join(Scheme, Scheme.id == DriverScheme.scheme_id)
        .where(DriverScheme.employee_id == employee_id)
        .order_by(DriverScheme.valid_from.desc())
    )
    return [
        {
            "scheme": {"id": str(s.public_id), "code": s.code, "name": s.name, "platform_id": s.platform_id},
            "valid_from": d.valid_from,
            "valid_to": d.valid_to,
            "source": d.source,
            "set_at": d.set_at,
        }
        for d, s in db.execute(q)
    ]


def scheme_of(db: Session, employee_id: int, month: date) -> Scheme | None:
    return for_month(db, [employee_id], month).get(employee_id)


# ------------------------------------------------------------------ requests from the app


def _request_out(db: Session, rows: list[SchemeChangeRequest]) -> list[dict]:
    ids = {i for r in rows for i in (r.current_scheme_id, r.requested_scheme_id) if i}
    schemes = {s.id: s for s in db.scalars(select(Scheme).where(Scheme.id.in_(ids)))} if ids else {}
    names = people.names(db, {r.employee_id for r in rows})

    def brief(i):
        s = schemes.get(i)
        return {"id": str(s.public_id), "code": s.code, "name": s.name} if s else None

    return [
        {
            "id": str(r.public_id),
            "employee": names.get(r.employee_id),
            "company_id": r.company_id,
            "current": brief(r.current_scheme_id),
            "requested": brief(r.requested_scheme_id),
            "effective_month": r.effective_month,
            "status": r.status,
            "driver_note": r.driver_note,
            "admin_note": r.admin_note,
            "created_at": r.created_at,
            "decided_at": r.decided_at,
            "version": r.version,
        }
        for r in rows
    ]


def driver_view(db: Session, employee_id: int) -> dict:
    """What the app shows: his platform's offered schemes with their terms, his scheme this month and next month,
    and his latest request."""
    driver = people.ref(db, employee_id)
    this, nxt = month_start(today()), add_months(month_start(today()), 1)
    now, upcoming = scheme_of(db, employee_id, this), scheme_of(db, employee_id, nxt)
    latest = db.scalar(
        select(SchemeChangeRequest)
        .where(SchemeChangeRequest.employee_id == employee_id, SchemeChangeRequest.status != "cancelled")
        .order_by(SchemeChangeRequest.id.desc())
        .limit(1)
    )
    offered = list_schemes(db, platform_id=driver.platform_id, offered_only=True) if driver.platform_id else []
    return {
        "current": _many(db, [now])[0] if now else None,
        "next_month": _many(db, [upcoming])[0] if upcoming and (not now or upcoming.id != now.id) else None,
        "schemes": offered,
        "request": _request_out(db, [latest])[0] if latest else None,
    }


def request_change(db: Session, employee_id: int, *, device_id: int, scheme_public_id, note: str | None) -> dict:
    driver = people.ref(db, employee_id)
    scheme = _by_public_id(db, scheme_public_id)
    if not (scheme.is_active and scheme.driver_selectable and scheme.platform_id == driver.platform_id):
        raise AppError(422, "scheme_not_available")
    month = add_months(month_start(today()), 1)
    upcoming = scheme_of(db, employee_id, month)
    if upcoming is not None and upcoming.id == scheme.id:
        raise AppError(422, "scheme_already_yours")
    r = SchemeChangeRequest(
        employee_id=employee_id,
        company_id=driver.company_id,
        current_scheme_id=upcoming.id if upcoming else None,
        requested_scheme_id=scheme.id,
        effective_month=month,
        driver_note=note,
        submitted_by_device=device_id,
    )
    db.add(r)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "scheme_change_requests_employee_id_idx":
            raise
        raise AppError(409, "scheme_request_pending") from None
    db.refresh(r)
    audit.record(
        db,
        action="scheme_request.submitted",
        entity_type="scheme_request",
        entity_id=r.public_id,
        actor_type="device",
        company_id=r.company_id,
        after={"scheme": str(scheme.public_id), "from": month.isoformat()},
    )
    db.commit()
    return driver_view(db, employee_id)


def cancel(db: Session, employee_id: int, public_id) -> dict:
    r = db.scalar(
        select(SchemeChangeRequest)
        .where(SchemeChangeRequest.public_id == public_id, SchemeChangeRequest.employee_id == employee_id)
        .with_for_update()
    )
    if r is None:
        raise AppError(404, "scheme_request_not_found")
    if r.status != "pending":
        raise AppError(409, "scheme_request_decided")
    r.status = "cancelled"
    r.version += 1
    audit.record(
        db,
        action="scheme_request.cancelled",
        entity_type="scheme_request",
        entity_id=r.public_id,
        actor_type="device",
        company_id=r.company_id,
    )
    db.commit()
    return driver_view(db, employee_id)


def _scoped(q, all_companies: bool, company_ids):
    return q if all_companies else q.where(SchemeChangeRequest.company_id.in_(list(company_ids)))


def list_requests(
    db: Session, *, status: str | None, limit: int = 50, offset: int = 0, all_companies: bool, company_ids
) -> list[dict]:
    q = (
        select(SchemeChangeRequest)
        .order_by(SchemeChangeRequest.created_at.desc(), SchemeChangeRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        q = q.where(SchemeChangeRequest.status == status)
    return _request_out(db, list(db.scalars(_scoped(q, all_companies, company_ids))))


def request_counts(db: Session, *, all_companies: bool, company_ids) -> dict:
    q = select(func.count()).select_from(SchemeChangeRequest).where(SchemeChangeRequest.status == "pending")
    return {"pending": db.scalar(_scoped(q, all_companies, company_ids))}


def _pending(db: Session, public_id, *, version: int | None, all_companies: bool, company_ids) -> SchemeChangeRequest:
    q = select(SchemeChangeRequest).where(SchemeChangeRequest.public_id == public_id)
    r = db.scalar(_scoped(q, all_companies, company_ids).with_for_update())
    if r is None:
        raise AppError(404, "scheme_request_not_found")
    if r.status != "pending":
        raise AppError(409, "scheme_request_decided")
    if version is not None and r.version != version:
        raise AppError(409, "version_conflict")
    return r


def _notify(db: Session, driver: people.EmployeeRef, key: str, **params) -> None:
    """Best effort: the decision stands even if WhatsApp is down (the app shows it too)."""
    if not driver.phone:
        return
    try:
        integrations.messenger(db).send(driver.phone, i18n.for_drivers(db, key, name=driver.name, **params))
    except messaging.DeliveryError as exc:
        log.warning("scheme decision not delivered: %s", exc)


def approve(
    db: Session, public_id, *, version: int | None, month: date | None, note: str | None, actor_user_id: int, **scope
) -> dict:
    r = _pending(db, public_id, version=version, **scope)
    driver = people.ref(db, r.employee_id)
    scheme = db.get(Scheme, r.requested_scheme_id)
    if not scheme.is_active or scheme.platform_id != driver.platform_id:
        raise AppError(409, "scheme_not_available")  # changed since the driver asked: reject it with the reason
    start = max(r.effective_month, month_start(month)) if month else r.effective_month
    for _ in range(24):  # the first month with no approved payroll
        if not _locked_from(db, driver.company_id, start):
            break
        start = add_months(start, 1)
    assign(db, driver, scheme, start, source="request", actor_user_id=actor_user_id, request=r)
    r.status, r.effective_month, r.admin_note = "approved", start, note
    r.decided_by, r.decided_at = actor_user_id, utcnow()
    r.version += 1
    audit.record(
        db,
        action="scheme_request.approved",
        entity_type="scheme_request",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        company_id=r.company_id,
        after={"scheme": str(scheme.public_id), "from": start.isoformat(), "note": note},
    )
    db.commit()
    _notify(db, driver, "messages.scheme_approved", scheme=scheme.name, month=start.strftime("%m-%Y"))
    return _request_out(db, [r])[0]


def reject(db: Session, public_id, *, version: int | None, note: str, actor_user_id: int, **scope) -> dict:
    r = _pending(db, public_id, version=version, **scope)
    r.status, r.admin_note, r.decided_by, r.decided_at = "rejected", note, actor_user_id, utcnow()
    r.version += 1
    audit.record(
        db,
        action="scheme_request.rejected",
        entity_type="scheme_request",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        company_id=r.company_id,
        after={"note": note},
    )
    db.commit()
    _notify(db, people.ref(db, r.employee_id), "messages.scheme_rejected", reason=note)
    return _request_out(db, [r])[0]
