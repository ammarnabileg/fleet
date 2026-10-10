"""Pay schemes as data (docs/payroll-schemes.md): what each platform offers, who is on which scheme month by month,
and the drivers' requests from the app to change it, decided in the dashboard.

- A scheme names its calculator (calculators.py) and holds its numbers by version, each from a month: a change of
  terms is a new version from a month no approved payroll has paid on the scheme, and a run reads the version of its
  own month, so a month is never recomputed on a price it did not have. The calculator itself does not change once
  the scheme is used (another shape of rule is another scheme).
- A driver's scheme runs from the first of a month; assigning from a month replaces what was set from it on. A month
  whose payroll is approved (or any later one) is never reassigned.
- A request from the app is for the next month, one open request per driver; approving it moves the driver from the
  first month that has no approved payroll yet.
"""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import messaging
from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.integrations import service as integrations
from app.modules.notifications import service as notifications
from app.modules.payroll.calculators import Rules, Step
from app.modules.payroll.models import (
    DriverScheme,
    Line,
    Platform,
    Run,
    Scheme,
    SchemeChangeRequest,
    SchemeStep,
    SchemeVersion,
)
from app.modules.payroll.service import add_months, month_start
from app.modules.people import service as people

log = logging.getLogger(__name__)

STEP_KINDS = {
    "platform_rates": set(),
    "per_order": set(),
    "batch": {"batch_rate"},
    "tiered_target": {"tier_bonus", "marks_deduction", "marks_reduce"},
}
TERMS_BY_VERSION = (  # what a driver is paid on: a change is a new version from a month
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
PRICES = ("calculator", *TERMS_BY_VERSION)
TERMS = ("name", "description", "is_active", "driver_selectable")


# ------------------------------------------------------------------ schemes and their versions


def _step_out(st: dict) -> dict:
    amount = st.get("amount")
    return {
        "kind": st["kind"],
        "threshold": Decimal(str(st["threshold"])),
        "amount": None if amount is None else Decimal(str(amount)),
    }


def _steps_json(steps) -> list[dict]:
    """A version's steps as stored: exact decimals as text, in a stable order."""
    rows = [
        {
            "kind": st["kind"],
            "threshold": str(Decimal(str(st["threshold"])).quantize(Decimal("0.001"))),
            "amount": None if st.get("amount") is None else str(Decimal(str(st["amount"])).quantize(Decimal("0.001"))),
        }
        for st in steps or []
    ]
    return sorted(rows, key=lambda x: (x["kind"], Decimal(x["threshold"])))


def _versions(db: Session, scheme_ids) -> dict[int, list[SchemeVersion]]:
    """Each scheme's versions, oldest month first."""
    out: dict[int, list[SchemeVersion]] = {i: [] for i in scheme_ids}
    if out:
        q = select(SchemeVersion).where(SchemeVersion.scheme_id.in_(list(out)))
        for v in db.scalars(q.order_by(SchemeVersion.effective_month)):
            out[v.scheme_id].append(v)
    return out


def _effective(versions: list[SchemeVersion], month: date) -> SchemeVersion:
    """The version a month is paid on: the latest from that month or before it; the first one covers any month
    before it (a scheme set up after the drivers were already on it)."""
    month = month_start(month)
    found = [v for v in versions if v.effective_month <= month]
    return found[-1] if found else versions[0]


def _terms(v: SchemeVersion) -> dict:
    return {k: getattr(v, k) for k in TERMS_BY_VERSION} | {"steps": [_step_out(x) for x in v.steps or []]}


def _rules(s: Scheme, v: SchemeVersion) -> Rules:
    by_kind: dict[str, list[Step]] = {}
    for st in sorted((_step_out(x) for x in v.steps or []), key=lambda x: x["threshold"]):
        by_kind.setdefault(st["kind"], []).append(Step(st["threshold"], st["amount"]))
    return Rules(
        calculator=s.calculator,
        per_order=v.per_order,
        target_orders=v.target_orders,
        missing_order_rate=v.missing_order_rate,
        reduced_rate=v.reduced_rate,
        bonus_when_reduced=v.bonus_when_reduced,
        marks_when_reduced=v.marks_when_reduced,
        floor_at_zero=v.floor_at_zero,
        steps=by_kind,
    )


def rules_for(db: Session, schemes: dict[int, Scheme], month: date) -> dict[int, tuple[Rules, int]]:
    """Each scheme's rules for the month, with the number of the version they come from."""
    versions = _versions(db, schemes)
    out = {}
    for i, s in schemes.items():
        v = _effective(versions[i], month)
        out[i] = (_rules(s, v), v.version_no)
    return out


def covers_of(db: Session, scheme: Scheme, month: date) -> list[str]:
    """What the scheme puts on the company in that month (its version of that month)."""
    return list(_effective(_versions(db, [scheme.id])[scheme.id], month).company_covers or [])


def _counts(db: Session, month: date) -> dict[int, int]:
    q = (
        select(DriverScheme.scheme_id, func.count())
        .where(DriverScheme.valid_from <= month, or_(DriverScheme.valid_to.is_(None), DriverScheme.valid_to > month))
        .group_by(DriverScheme.scheme_id)
    )
    return dict(db.execute(q).all())


def _last_paid(db: Session, scheme_ids) -> dict[int, date]:
    """The latest month an approved (or paid) payroll paid each scheme on."""
    ids = list(scheme_ids)
    if not ids:
        return {}
    q = (
        select(Line.scheme_id, func.max(Run.month))
        .join(Run, Run.id == Line.run_id)
        .where(Line.scheme_id.in_(ids), Run.status != "draft")
        .group_by(Line.scheme_id)
    )
    return dict(db.execute(q).all())


def _used_ids(db: Session, scheme_ids) -> set[int]:
    """Schemes a driver was ever put on, or a payroll line used."""
    ids = list(scheme_ids)
    if not ids:
        return set()
    on = set(db.scalars(select(DriverScheme.scheme_id).where(DriverScheme.scheme_id.in_(ids)).distinct()))
    return on | set(db.scalars(select(Line.scheme_id).where(Line.scheme_id.in_(ids)).distinct()))


def _change_from(versions: list[SchemeVersion], last_paid: date | None) -> date:
    """The earliest month a change of terms may take effect: after the last month paid on the scheme, and not before
    its latest version (from that same month the latest version is replaced)."""
    earliest = versions[-1].effective_month
    return max(earliest, add_months(last_paid, 1)) if last_paid else earliest


def _version_out(v: SchemeVersion, users: dict[int, str]) -> dict:
    return {
        "version_no": v.version_no,
        "effective_month": v.effective_month,
        **_terms(v),
        "note": v.note,
        "created_at": v.created_at,
        "created_by": users.get(v.created_by),
    }


def _out(
    s: Scheme,
    versions: list[SchemeVersion],
    counts: dict[int, int],
    month: date,
    *,
    used: bool,
    last_paid: date | None,
    users: dict[int, str],
) -> dict:
    v = _effective(versions, month)
    later = [x for x in versions if x.effective_month > month_start(month)]
    return {
        "id": str(s.public_id),
        "platform_id": s.platform_id,
        "code": s.code,
        "name": s.name,
        "description": s.description,
        "calculator": s.calculator,
        **_terms(v),  # this month's terms
        "driver_selectable": s.driver_selectable,
        "is_active": s.is_active,
        "drivers": counts.get(s.id, 0),  # on it this month
        "version": s.version,
        "version_no": v.version_no,
        "effective_month": v.effective_month,
        "next_version": {"version_no": later[0].version_no, "effective_month": later[0].effective_month}
        if later
        else None,
        "used": used,
        "change_from": _change_from(versions, last_paid),
        "versions": [_version_out(x, users) for x in reversed(versions)],  # the newest first
    }


def _many(db: Session, rows: list[Scheme]) -> list[dict]:
    ids = [s.id for s in rows]
    versions = _versions(db, ids)
    month = month_start(today())
    counts = _counts(db, month)
    used, paid = _used_ids(db, ids), _last_paid(db, ids)
    users = identity.user_names(db, {v.created_by for vs in versions.values() for v in vs if v.created_by})
    return [
        _out(s, versions[s.id], counts, month, used=s.id in used, last_paid=paid.get(s.id), users=users) for s in rows
    ]


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
        key = (st["kind"], Decimal(str(st["threshold"])))
        if key in seen:
            raise AppError(422, "scheme_step_invalid", kind=st["kind"])
        seen.add(key)
    if calc == "batch" and not any(st["kind"] == "batch_rate" for st in steps):
        raise AppError(422, "field_required", field="steps")


def _same(a: dict, b: dict) -> bool:
    for k in TERMS_BY_VERSION:
        x, y = a.get(k), b.get(k)
        if k == "company_covers":
            x, y = sorted(x or []), sorted(y or [])
        if x != y:
            return False
    return _steps_json(a["steps"]) == _steps_json(b["steps"])


def _mirror(db: Session, s: Scheme, terms: dict) -> None:
    """The scheme's own columns and steps hold its latest version."""
    for k in TERMS_BY_VERSION:
        setattr(s, k, terms[k])
    db.execute(delete(SchemeStep).where(SchemeStep.scheme_id == s.id))
    for st in terms["steps"]:
        db.add(SchemeStep(scheme_id=s.id, kind=st["kind"], threshold=st["threshold"], amount=st.get("amount")))


def _new_version(db: Session, s: Scheme, no: int, month: date, terms: dict, *, note, actor_user_id) -> SchemeVersion:
    v = SchemeVersion(
        scheme_id=s.id,
        version_no=no,
        effective_month=month,
        **{k: terms[k] for k in TERMS_BY_VERSION},
        steps=_steps_json(terms["steps"]),
        note=note,
        created_by=actor_user_id,
    )
    db.add(v)
    return v


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
    terms = {k: getattr(s, k) for k in TERMS_BY_VERSION} | {"steps": steps}
    _new_version(db, s, 1, month_start(today()), terms, note=None, actor_user_id=actor_user_id)
    db.flush()
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
    """The name, description and flags change in place. A change of terms is a new version from a month (the editor's
    «يسري من»): never a month an approved payroll paid on this scheme, never before its latest version (from that same
    month the latest version is replaced). A scheme nobody was ever on is simply redefined."""
    s = _by_public_id(db, public_id, lock=True)
    if s.version != version:
        raise AppError(409, "version_conflict")
    changes = dict(changes)
    month = changes.pop("effective_month", None)
    note = changes.pop("version_note", None)
    used = bool(_used_ids(db, [s.id]))
    calc_change = changes.get("calculator", s.calculator) != s.calculator
    if not calc_change:
        changes.pop("calculator", None)
    if calc_change and used:
        raise AppError(409, "scheme_in_use")  # another shape of rule is another scheme
    versions = _versions(db, [s.id])[s.id]
    new_terms = {k: v for k, v in changes.items() if k in (*TERMS_BY_VERSION, "steps")}
    if "name" in changes:
        changes["name"] = i18n.validate_localized(db, changes["name"])
    if changes.get("description"):
        changes["description"] = i18n.validate_localized(db, changes["description"])
    before = {k: getattr(s, k) for k in changes if k not in (*TERMS_BY_VERSION, "steps")}
    for k in ("name", "description", "is_active", "driver_selectable"):
        if k in changes:
            setattr(s, k, changes[k])
    after_terms = None
    terms = _terms(versions[-1]) | new_terms
    if calc_change or not _same(terms, _terms(versions[-1])):
        if calc_change or (month is None and not used):  # redefined: one version, from its first month
            calc = changes["calculator"] if calc_change else s.calculator
            _check(terms | {"calculator": calc})
            target = versions[0].effective_month
            before["terms"] = _terms(versions[-1])
            for v in versions:
                db.delete(v)
            db.flush()
            s.calculator = calc
            _new_version(db, s, 1, target, terms, note=note, actor_user_id=actor_user_id)
        else:
            if month is None:
                raise AppError(422, "field_required", field="effective_month")
            target = month_start(month)
            earliest = _change_from(versions, _last_paid(db, [s.id]).get(s.id))
            if target < earliest:
                raise AppError(409, "scheme_version_month", **{"from": earliest.isoformat()[:7]})
            _check(terms | {"calculator": s.calculator})
            before["terms"] = _terms(_effective(versions, target))
            latest = versions[-1]
            no = latest.version_no + 1
            if target == latest.effective_month:  # the latest version, not paid on yet, is replaced
                no = latest.version_no
                db.delete(latest)
                db.flush()
            _new_version(db, s, no, target, terms, note=note, actor_user_id=actor_user_id)
        db.flush()
        _mirror(db, s, _terms(_versions(db, [s.id])[s.id][-1]))
        after_terms = {"from": target.isoformat(), **terms}
    s.version += 1
    db.flush()
    audit.record(
        db,
        action="scheme.updated",
        entity_type="scheme",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after={k: v for k, v in changes.items() if k not in (*TERMS_BY_VERSION, "steps")}
        | ({"terms": after_terms, "note": note} if after_terms else {}),
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
    # the first version covers every month the scheme is used in: a driver put on it from a month before the first
    # version takes that version back to his month (so a later version from the first one's month cannot reach his)
    db.execute(
        sql_update(SchemeVersion)
        .where(
            SchemeVersion.scheme_id == scheme.id,
            SchemeVersion.version_no == 1,
            SchemeVersion.effective_month > month,
        )
        .values(effective_month=month)
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
    notifications.notify_driver(
        db,
        r.employee_id,
        "scheme_request_approved",
        params={"scheme": scheme.name, "month": start.strftime("%m-%Y")},
        entity_type="scheme_request",
        entity_id=r.public_id,
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
    scheme = db.get(Scheme, r.requested_scheme_id)
    notifications.notify_driver(
        db,
        r.employee_id,
        "scheme_request_rejected",
        params={"scheme": scheme.name, "reason": note},
        entity_type="scheme_request",
        entity_id=r.public_id,
    )
    db.commit()
    _notify(db, people.ref(db, r.employee_id), "messages.scheme_rejected", reason=note)
    return _request_out(db, [r])[0]
