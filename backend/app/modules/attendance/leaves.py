"""Leaves and absence requests (طلب التغيب), on configurable leave types.

Each leave type (attendance.leave_types) carries its rules: the pay tiers its days run through, the most days per
occurrence, per service year and per service, the months of service needed, once per service, a required attachment,
the gender it applies to, and whether it counts calendar or working days. The seeded values are defaults read from
the Kuwait private-sector labour law (Law No. 6 of 2010): «قيم افتراضية حسب قانون العمل — راجعها مع الموارد
البشرية/المستشار القانوني». The office edits them.

A leave is registered by the office (approved at once if it was agreed) or requested by the driver from the app (a
resend with the same client_ref returns the request already made). Both go through the same check (`evaluate`):
eligibility, limits, balance, and the paid/unpaid split of its days along the tiers (sick days run through the service
year's tiers in order: what earlier sick leaves of that year used comes first). A driver's request that breaks a rule
is refused with the reason; the office may register it all the same (`override`, audited), and where the data to
check is missing (no hire date, no gender, the certificate still to come) the office is warned, not stopped. The
split is computed again when the leave is approved (other leaves may have been approved meanwhile), and the office
may make an emergency or other leave paid. Approval and refusal stay with the leaves.approve permission (leaves do not
go through the approval workflows); a refusal always has its reason, and every step is in the audit log.

Each request has a follow-up date (the day it was made, unless the user enters another): once the leaves settings'
`absence_followup_days` have passed since it, a daily scan raises one office alert per request still open (pending or
approved, not followed up). The office marks it followed up; a cancel or refusal closes the alert too.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.attendance import rules
from app.modules.attendance.models import Leave, LeaveType
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

MAX_LEAVE_DAYS = 200  # maternity: 70 days and up to four months more
FOLLOWUP_RANGE = timedelta(days=366)  # the follow-up date: at most a year before or after today
OPEN = ("pending", "approved")
TYPE_FIELDS = (
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
# rules the office is only warned about, where the data to check them may be missing
SOFT_FOR_OFFICE = {"hire_date_unknown", "leave_attachment_required"}


def span(first: date, last: date, limit: int) -> None:
    if last < first:
        raise AppError(422, "invalid_range")
    if (last - first).days >= limit:
        raise AppError(422, "range_too_long_days", days=limit)


def unlocked(db: Session, company_id: int, days: Iterable[date]) -> None:
    """Refuses a change touching a month whose payroll is approved or paid."""
    from app.modules.payroll import service as payroll  # payroll reads this module: imported when used

    for month in sorted({d.replace(day=1) for d in days}):
        if payroll.month_locked(db, company_id, month):
            raise AppError(409, "payroll_locked")


def scoped(q, column, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(column.in_(list(company_ids)))


def policy(db: Session):
    return org.get_section(db, "leaves")


# ------------------------------------------------------------------ leave types


def _type_out(t: LeaveType) -> dict:
    return {"code": t.code, **{f: getattr(t, f) for f in TYPE_FIELDS}, "version": t.version, "updated_at": t.updated_at}


def types_by_code(db: Session) -> dict[str, LeaveType]:
    return {t.code: t for t in db.scalars(select(LeaveType).order_by(LeaveType.sort_order, LeaveType.code))}


def list_types(db: Session) -> list[dict]:
    return [_type_out(t) for t in types_by_code(db).values()]


def _check_tiers(tiers: list[dict]) -> None:
    for i, t in enumerate(tiers):
        if t.get("days") is None and i != len(tiers) - 1:
            raise AppError(422, "leave_tiers_open_end")  # only the last tier may have no end


def update_type(db: Session, code: str, changes: dict, *, version: int, actor_user_id: int) -> dict:
    t = db.scalar(select(LeaveType).where(LeaveType.code == code).with_for_update())
    if t is None:
        raise AppError(404, "leave_type_not_found")
    if t.version != version:
        raise AppError(409, "version_conflict")
    if "tiers" in changes:
        _check_tiers(changes["tiers"])
    before = _type_out(t)
    for k, v in changes.items():
        setattr(t, k, v)
    t.version += 1
    t.updated_by, t.updated_at = actor_user_id, utcnow()
    db.flush()
    audit.record(
        db,
        action="leave_type.updated",
        entity_type="leave_type",
        entity_id=code,
        actor_user_id=actor_user_id,
        before={k: before[k] for k in changes},
        after=changes,
    )
    db.commit()
    return _type_out(t)


def _type(db: Session, code: str) -> LeaveType:
    t = db.get(LeaveType, code)
    if t is None:
        raise AppError(422, "leave_type_not_found")
    return t


# ------------------------------------------------------------------ the rules


def _used(
    db: Session,
    employee_id: int,
    kind: str,
    lo: date | None = None,
    hi: date | None = None,
    *,
    exclude: int | None = None,
    before: date | None = None,
    statuses=OPEN,
) -> int:
    """The days counted by the employee's leaves of this kind (pending and approved: a request reserves its days),
    starting lo..hi."""
    q = select(func.coalesce(func.sum(Leave.counted_days), 0)).where(
        Leave.employee_id == employee_id, Leave.kind == kind, Leave.status.in_(statuses)
    )
    if lo is not None:
        q = q.where(Leave.date_from >= lo)
    if hi is not None:
        q = q.where(Leave.date_from <= hi)
    if exclude is not None:
        q = q.where(Leave.id != exclude)
    if before is not None:
        q = q.where(Leave.date_from < before)
    return int(db.scalar(q))


def _annual(db: Session, emp, t: LeaveType, on: date, *, exclude: int | None = None) -> dict:
    """Annual leave: earned pro rata from the hire date (max_per_year a year), less what was taken or requested; at
    most this year's entitlement and the carried-over years' (a setting) are kept."""
    per_year = t.max_per_year or 30
    earned = rules.accrued(emp.hire_date, on, per_year)
    used = _used(db, emp.id, t.code, exclude=exclude)
    if earned is None:
        return {"accrued": None, "used": used, "available": None}
    cap = per_year * (1 + policy(db).annual_carry_over_years)
    return {"accrued": earned, "used": used, "available": max(0, min(earned - used, cap))}


def evaluate(
    db: Session,
    emp,
    t: LeaveType,
    first: date,
    last: date,
    *,
    exclude: int | None = None,
    has_file: bool | None = None,
    paid: bool = False,
) -> dict:
    """What a leave of this type from first to last would be for the employee: the days it counts, its split along
    the pay tiers, and the rules it breaks (problems) or could not check (warnings)."""
    span(first, last, MAX_LEAVE_DAYS)
    p = policy(db)
    day_list = rules.counted(first, last, t.counts, p.weekend_days)
    n = len(day_list)
    problems: list[dict] = []
    warnings: list[str] = []

    def bad(code: str, **params) -> None:
        problems.append({"code": code, "params": params})

    if not t.active:
        bad("leave_type_inactive")
    if n == 0:
        bad("leave_no_working_days")
    if t.eligible_gender:
        if emp.gender is None:
            warnings.append("gender_unknown")
        elif emp.gender != t.eligible_gender:
            bad("leave_gender")
    hire = emp.hire_date
    if t.min_service_months:
        if hire is None:
            bad("hire_date_unknown")
        elif rules.months_between(hire, first) < t.min_service_months:
            bad("leave_service_too_short", months=t.min_service_months)
    if t.once_per_service and _used(db, emp.id, t.code, exclude=exclude) > 0:
        bad("leave_once_per_service")
    if t.max_per_occurrence and n > t.max_per_occurrence:
        bad("leave_too_long", max=t.max_per_occurrence)
    year_lo, year_hi = rules.service_year(hire, first)
    if t.max_per_year and not t.accrues:
        used = _used(db, emp.id, t.code, year_lo, year_hi, exclude=exclude)
        if used + n > t.max_per_year:
            bad("leave_year_limit", max=t.max_per_year, left=max(0, t.max_per_year - used))
    if t.max_per_service:
        used = _used(db, emp.id, t.code, exclude=exclude)
        if used + n > t.max_per_service:
            bad("leave_service_limit", max=t.max_per_service, left=max(0, t.max_per_service - used))
    balance = None
    if t.accrues:
        balance = _annual(db, emp, t, max(first, today()), exclude=exclude)
        if balance["available"] is not None and n > balance["available"]:
            bad("leave_balance", available=balance["available"])
    if has_file is False and t.requires_attachment:
        bad("leave_attachment_required")
    before = 0
    if t.tier_period == "service_year":
        before = _used(db, emp.id, t.code, year_lo, year_hi, exclude=exclude, before=first)
    tiers = [{"days": None, "pay_percent": 100}] if paid and t.office_may_pay else t.tiers
    parts = rules.split(n, tiers, before)
    return {
        "kind": t.code,
        "date_from": first,
        "date_to": last,
        "calendar_days": (last - first).days + 1,
        "days": n,
        "split": parts,
        "paid_days": sum(x["days"] for x in parts if x["pay_percent"] > 0),
        "unpaid_days": sum(x["days"] for x in parts if x["pay_percent"] == 0),
        "pay_days": str(sum(Decimal(x["days"] * x["pay_percent"]) / 100 for x in parts).quantize(Decimal("0.01"))),
        "tier_days_before": before,
        "balance": balance,
        "problems": problems,
        "warnings": warnings,
    }


def _refuse(problems: list[dict], *, office: bool) -> None:
    hard = [p for p in problems if not (office and p["code"] in SOFT_FOR_OFFICE)]
    if hard:
        raise AppError(422, hard[0]["code"], **hard[0]["params"])


def _clash(db: Session, employee_id: int, first: date, last: date, exclude: int | None = None) -> None:
    # one registration at a time per employee, so two overlapping leaves cannot both pass the check
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('attendance.leave:' || :e, 0))"), {"e": employee_id})
    q = select(Leave.public_id).where(
        Leave.employee_id == employee_id, Leave.status.in_(OPEN), Leave.date_from <= last, Leave.date_to >= first
    )
    if exclude is not None:
        q = q.where(Leave.id != exclude)
    clash = db.scalar(q)
    if clash is not None:
        raise AppError(409, "leave_overlaps", leave_id=str(clash))


def _followup(value: date | None) -> date:
    d = value or today()
    if abs(d - today()) > FOLLOWUP_RANGE:
        raise AppError(422, "followup_out_of_range")
    return d


def preview(db: Session, data: dict, *, employee=None, **scope) -> dict:
    emp = employee or people.ref_by_public_id(db, data["employee_id"], **scope)
    t = _type(db, data["kind"])
    out = evaluate(db, emp, t, data["date_from"], data["date_to"], paid=bool(data.get("paid")))
    return out


# ------------------------------------------------------------------ the office


def leave_out(db: Session, rows: list[Leave]) -> list[dict]:
    names = people.names(db, {r.employee_id for r in rows})
    users = identity.user_names(db, {u for r in rows for u in (r.created_by, r.decided_by, r.followed_up_by) if u})
    kinds = types_by_code(db)
    n = org.section_now(db, "leaves").absence_followup_days
    return [
        {
            "id": str(r.public_id),
            "employee": names.get(r.employee_id),
            "company_id": r.company_id,
            "kind": r.kind,
            "kind_name": kinds[r.kind].name if r.kind in kinds else None,
            "date_from": r.date_from,
            "date_to": r.date_to,
            "days": (r.date_to - r.date_from).days + 1,
            "counted_days": r.counted_days,
            "split": r.split,
            "unpaid_days": sum(x["days"] for x in r.split if x["pay_percent"] == 0),
            "paid_override": r.paid_override,
            "rules_overridden": r.rules_overridden,
            "source": r.source,
            "status": r.status,
            "note": r.note,
            "has_file": r.file_sha256 is not None,
            "file_sha256": r.file_sha256,
            "created_by": users.get(r.created_by),
            "created_at": r.created_at,
            "decided_by": users.get(r.decided_by),
            "decided_at": r.decided_at,
            "decision_note": r.decision_note,
            "cancel_reason": r.cancel_reason,
            "followup_from": r.followup_from,
            "followup_due": r.followup_from + timedelta(days=n),
            "followed_up_at": r.followed_up_at,
            "followed_up_by": users.get(r.followed_up_by),
            "version": r.version,
        }
        for r in rows
    ]


def get_row(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Leave:
    q = scoped(select(Leave).where(Leave.public_id == public_id), Leave.company_id, all_companies, company_ids)
    leave = db.scalar(q.with_for_update() if lock else q)
    if leave is None:
        raise AppError(404, "leave_not_found")
    return leave


def _audit(db: Session, action: str, leave: Leave, *, actor_user_id: int | None, after: dict | None = None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="leave",
        entity_id=leave.public_id,
        actor_user_id=actor_user_id,
        actor_type=None if actor_user_id else "device",
        company_id=leave.company_id,
        after={"kind": leave.kind, "from": leave.date_from, "to": leave.date_to, "status": leave.status}
        | (after or {}),
    )


def create_leave(db: Session, data: dict, *, approve: bool, actor_user_id: int, **scope) -> dict:
    """Registered by the office; approved at once when the user may approve leaves and asks to. A rule broken stops
    it unless the office overrides (audited); missing data only warns."""
    employee = people.ref_by_public_id(db, data["employee_id"], **scope)
    first, last = data["date_from"], data["date_to"]
    span(first, last, MAX_LEAVE_DAYS)
    t = _type(db, data["kind"])
    if data.get("file_sha256"):
        files.get(db, data["file_sha256"])  # a medical certificate, a ticket
    _clash(db, employee.id, first, last)
    paid = bool(data.get("paid")) and approve
    ev = evaluate(db, employee, t, first, last, has_file=bool(data.get("file_sha256")), paid=paid)
    override = bool(data.get("override"))
    if not override:
        _refuse(ev["problems"], office=True)
    if approve:
        unlocked(db, employee.company_id, rules.days(first, last))
    leave = Leave(
        employee_id=employee.id,
        company_id=employee.company_id,
        kind=t.code,
        date_from=first,
        date_to=last,
        note=data.get("note"),
        file_sha256=data.get("file_sha256"),
        created_by=actor_user_id,
        status="approved" if approve else "pending",
        decided_by=actor_user_id if approve else None,
        decided_at=utcnow() if approve else None,
        counted_days=ev["days"],
        split=ev["split"],
        paid_override=paid and t.office_may_pay,
        rules_overridden=override and bool(ev["problems"]),
        followup_from=_followup(data.get("followup_from")),
    )
    db.add(leave)
    db.flush()
    _followup_now(db, leave)
    _audit(
        db,
        "leave.approved" if approve else "leave.registered",
        leave,
        actor_user_id=actor_user_id,
        after={"split": ev["split"], "overridden": [p["code"] for p in ev["problems"]] if override else []},
    )
    db.commit()
    db.refresh(leave)
    return leave_out(db, [leave])[0]


def _notify(db: Session, leave: Leave, kind: str, **params) -> None:
    emp = people.ref(db, leave.employee_id)
    if emp is None or not emp.is_driver:
        return
    t = db.get(LeaveType, leave.kind)
    notifications.notify_driver(
        db,
        leave.employee_id,
        kind,
        params={"kind": t.name, "from": leave.date_from.isoformat(), "to": leave.date_to.isoformat(), **params},
        entity_type="leave",
        entity_id=leave.public_id,
        dedupe_key=f"{kind}:{leave.id}",
    )


def _close_alerts(db: Session, leave: Leave, kinds=("leave_requested", "absence_followup")) -> None:
    notifications.resolve_entity(db, "leave", leave.public_id, kinds)


def decide_leave(
    db: Session, public_id, *, approve: bool, note: str | None, actor_user_id: int, paid: bool = False, **scope
) -> dict:
    leave = get_row(db, public_id, lock=True, **scope)
    if leave.status != "pending":
        raise AppError(409, "leave_not_pending", status=leave.status)
    if approve:
        unlocked(db, leave.company_id, rules.days(leave.date_from, leave.date_to))
        t = db.get(LeaveType, leave.kind)
        ev = evaluate(
            db, people.ref(db, leave.employee_id), t, leave.date_from, leave.date_to, exclude=leave.id, paid=paid
        )
        leave.counted_days, leave.split = ev["days"], ev["split"]
        leave.paid_override = paid and t.office_may_pay
    elif not note:
        raise AppError(422, "reason_required")
    leave.status = "approved" if approve else "rejected"
    leave.decided_by, leave.decided_at, leave.decision_note = actor_user_id, utcnow(), note
    leave.version += 1
    _audit(db, f"leave.{leave.status}", leave, actor_user_id=actor_user_id, after={"note": note, "split": leave.split})
    if approve:
        _close_alerts(db, leave, ("leave_requested",))
        _notify(db, leave, "leave_approved")
    else:
        _close_alerts(db, leave)
        _notify(db, leave, "leave_rejected", reason=note)
    db.commit()
    return leave_out(db, [leave])[0]


def cancel_leave(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    leave = get_row(db, public_id, lock=True, **scope)
    if leave.status not in OPEN:
        raise AppError(409, "leave_not_open", status=leave.status)
    if leave.status == "approved":  # its days counted in an approved payroll stay counted
        unlocked(db, leave.company_id, rules.days(leave.date_from, leave.date_to))
    leave.status, leave.cancel_reason = "cancelled", reason
    leave.version += 1
    _audit(db, "leave.cancelled", leave, actor_user_id=actor_user_id, after={"reason": reason})
    _close_alerts(db, leave)
    db.commit()
    return leave_out(db, [leave])[0]


def set_followup_from(db: Session, public_id, *, day: date, actor_user_id: int, **scope) -> dict:
    """The date the follow-up counts from, changed: an alert raised already closes if it is no longer due (the scan
    raises it again when it is)."""
    leave = get_row(db, public_id, lock=True, **scope)
    old = leave.followup_from
    leave.followup_from = _followup(day)
    leave.version += 1
    if leave.followup_from + timedelta(days=org.section_now(db, "leaves").absence_followup_days) > today():
        _close_alerts(db, leave, ("absence_followup",))
    else:
        _followup_now(db, leave)
    audit.record(
        db,
        action="leave.followup_date",
        entity_type="leave",
        entity_id=leave.public_id,
        actor_user_id=actor_user_id,
        company_id=leave.company_id,
        before={"followup_from": old},
        after={"followup_from": leave.followup_from},
    )
    db.commit()
    return leave_out(db, [leave])[0]


def mark_followed_up(db: Session, public_id, *, note: str | None, actor_user_id: int, **scope) -> dict:
    leave = get_row(db, public_id, lock=True, **scope)
    if leave.followed_up_at is not None:
        raise AppError(409, "leave_followed_up")
    leave.followed_up_at, leave.followed_up_by = utcnow(), actor_user_id
    leave.version += 1
    _close_alerts(db, leave, ("absence_followup",))
    _audit(db, "leave.followed_up", leave, actor_user_id=actor_user_id, after={"note": note})
    db.commit()
    return leave_out(db, [leave])[0]


def _raise_followup(db: Session, r: Leave, names: dict, kinds: dict) -> bool:
    return notifications.raise_alert(
        db,
        "absence_followup",
        company_id=r.company_id,
        entity_type="leave",
        entity_id=r.public_id,
        params={
            "driver": (names.get(r.employee_id) or {}).get("name", ""),
            "kind": kinds[r.kind].name,
            "from": r.date_from.isoformat(),
            "to": r.date_to.isoformat(),
            "days": (today() - r.followup_from).days,
        },
        dedupe_key=f"absence_followup:{r.id}",
    )


def _followup_now(db: Session, r: Leave) -> None:
    """A follow-up date entered already the settings' days back: the alert is raised at once, not the next morning."""
    n = org.section_now(db, "leaves").absence_followup_days
    if r.status in OPEN and r.followed_up_at is None and r.followup_from + timedelta(days=n) <= today():
        _raise_followup(db, r, people.names(db, {r.employee_id}), types_by_code(db))


def scan_followups(db: Session) -> int:
    """Daily: one office alert per open request whose follow-up date is the settings' days behind."""
    n = org.section_now(db, "leaves").absence_followup_days
    due = today() - timedelta(days=n)
    rows = list(
        db.scalars(
            select(Leave).where(Leave.status.in_(OPEN), Leave.followed_up_at.is_(None), Leave.followup_from <= due)
        )
    )
    names = people.names(db, {r.employee_id for r in rows})
    kinds = types_by_code(db)
    raised = sum(_raise_followup(db, r, names, kinds) for r in rows)
    db.commit()
    return raised


def list_leaves(
    db: Session,
    *,
    status: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    employee_id=None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = scoped(select(Leave), Leave.company_id, **scope)
    if status:
        q = q.where(Leave.status.in_(status.split(",")))
    if kind:
        q = q.where(Leave.kind.in_(kind.split(",")))
    if source:
        q = q.where(Leave.source == source)
    if employee_id is not None:
        q = q.where(Leave.employee_id == people.ref_by_public_id(db, employee_id, **scope).id)
    if date_from is not None:
        q = q.where(Leave.date_to >= date_from)
    if date_to is not None:
        q = q.where(Leave.date_from <= date_to)
    rows = db.scalars(q.order_by(Leave.date_from.desc(), Leave.id.desc()).limit(min(limit, 500)).offset(offset))
    return leave_out(db, list(rows))


def pending_count(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> int:
    q = scoped(select(func.count()).select_from(Leave), Leave.company_id, all_companies, company_ids)
    return db.scalar(q.where(Leave.status == "pending"))


# ------------------------------------------------------------------ balances


def balances(db: Session, emp, *, driver: bool = False) -> list[dict]:
    """Per active type: whether he may take it now, what he used this service year and in his service, and what is
    left (annual: earned and available)."""
    on = today()
    lo, hi = rules.service_year(emp.hire_date, on)
    out = []
    for t in types_by_code(db).values():
        if not t.active or (driver and not t.driver_may_request):
            continue
        ev = evaluate(db, emp, t, on, on)
        reasons = [
            p["code"]
            for p in ev["problems"]
            if p["code"] in {"leave_gender", "hire_date_unknown", "leave_service_too_short", "leave_once_per_service"}
        ]
        used_year = _used(db, emp.id, t.code, lo, hi)
        used_service = _used(db, emp.id, t.code)
        row = {
            "code": t.code,
            "name": t.name,
            "eligible": not reasons,
            "reason": reasons[0] if reasons else None,
            "requires_attachment": t.requires_attachment,
            "tiers": t.tiers,
            "counts": t.counts,
            "max_per_occurrence": t.max_per_occurrence,
            "used_year": used_year,
            "used_service": used_service,
            "pending": _used(db, emp.id, t.code, statuses=("pending",)),
            "service_year": {"from": lo, "to": hi},
            "left_year": None,
            "left_service": None,
            "accrued": None,
            "available": None,
        }
        if t.max_per_year and not t.accrues:
            row["left_year"] = max(0, t.max_per_year - used_year)
        if t.max_per_service:
            row["left_service"] = max(0, t.max_per_service - used_service)
        if t.accrues:
            a = _annual(db, emp, t, on)
            row["accrued"], row["available"] = a["accrued"], a["available"]
        out.append(row)
    return out


def employee_balances(db: Session, public_id, **scope) -> list[dict]:
    return balances(db, people.ref_by_public_id(db, public_id, **scope))


# ------------------------------------------------------------------ the driver


def _driver_out(db: Session, rows: list[Leave]) -> list[dict]:
    kinds = types_by_code(db)
    return [
        {
            "id": str(r.public_id),
            "kind": r.kind,
            "kind_name": kinds[r.kind].name,
            "date_from": r.date_from,
            "date_to": r.date_to,
            "days": r.counted_days,
            "split": r.split,
            "status": r.status,
            "reason": r.note,
            "decision_note": r.decision_note,
            "cancel_reason": r.cancel_reason,
            "followup_from": r.followup_from,
            "has_file": r.file_sha256 is not None,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def driver_view(db: Session, employee_id: int) -> dict:
    emp = people.ref(db, employee_id)
    rows = list(
        db.scalars(
            select(Leave)
            .where(Leave.employee_id == employee_id)
            .order_by(Leave.created_at.desc(), Leave.id.desc())
            .limit(30)
        )
    )
    return {"types": [b for b in balances(db, emp, driver=True) if b["eligible"]], "requests": _driver_out(db, rows)}


def driver_preview(db: Session, employee_id: int, data: dict) -> dict:
    emp = people.ref(db, employee_id)
    t = _type(db, data["kind"])
    if not t.driver_may_request:
        raise AppError(422, "leave_type_not_found")
    return evaluate(db, emp, t, data["date_from"], data["date_to"])


def _check_attachment(db: Session, sha: str, device_id: int) -> None:
    info = files.get(db, sha)
    if info.uploaded_by_device != device_id:
        raise AppError(422, "file_not_yours")


def driver_request(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    """From the app: refused with its reason when a rule is broken. A resend (the same client_ref) answers with the
    request already made."""
    existing = db.scalar(select(Leave).where(Leave.client_ref == data["client_ref"]))
    if existing is not None:
        if existing.employee_id != employee_id:
            raise AppError(409, "leave_exists")
        return _driver_out(db, [existing])[0]
    emp = people.ref(db, employee_id)
    t = _type(db, data["kind"])
    if not t.driver_may_request:
        raise AppError(422, "leave_type_not_found")
    first, last = data["date_from"], data["date_to"]
    span(first, last, MAX_LEAVE_DAYS)
    if data.get("file_sha256"):
        _check_attachment(db, data["file_sha256"], device_id)
    _clash(db, emp.id, first, last)
    ev = evaluate(db, emp, t, first, last, has_file=bool(data.get("file_sha256")))
    _refuse(ev["problems"], office=False)
    leave = Leave(
        employee_id=emp.id,
        company_id=emp.company_id,
        kind=t.code,
        date_from=first,
        date_to=last,
        note=data.get("reason") or None,
        file_sha256=data.get("file_sha256"),
        created_by_device=device_id,
        source="driver",
        client_ref=data["client_ref"],
        counted_days=ev["days"],
        split=ev["split"],
        followup_from=_followup(data.get("followup_from")),
    )
    try:
        with db.begin_nested():
            db.add(leave)
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "leaves_client_ref_key":
            raise AppError(409, "leave_exists") from None
        raise
    db.refresh(leave)
    notifications.raise_alert(
        db,
        "leave_requested",
        company_id=leave.company_id,
        entity_type="leave",
        entity_id=leave.public_id,
        params={
            "driver": emp.name,
            "kind": t.name,
            "from": first.isoformat(),
            "to": last.isoformat(),
            "days": ev["days"],
        },
        dedupe_key=f"leave_requested:{leave.id}",
    )
    _followup_now(db, leave)
    _audit(db, "leave.requested", leave, actor_user_id=None, after={"split": ev["split"]})
    db.commit()
    return _driver_out(db, [leave])[0]


def driver_cancel(db: Session, public_id, *, employee_id: int) -> dict:
    """He withdraws his request while it waits; a resend finds it withdrawn already."""
    leave = db.scalar(
        select(Leave).where(Leave.public_id == public_id, Leave.employee_id == employee_id).with_for_update()
    )
    if leave is None:
        raise AppError(404, "leave_not_found")
    if leave.status == "cancelled":
        return _driver_out(db, [leave])[0]
    if leave.status != "pending":
        raise AppError(409, "leave_not_pending", status=leave.status)
    leave.status, leave.cancel_reason = "cancelled", "withdrawn by the driver"
    leave.version += 1
    _audit(db, "leave.withdrawn", leave, actor_user_id=None)
    _close_alerts(db, leave)
    db.commit()
    return _driver_out(db, [leave])[0]


# ------------------------------------------------------------------ for payroll and the days to classify


def leave_days(db: Session, ids: list[int], first: date, last: date) -> tuple[dict, dict, dict]:
    """Per employee, first to last, the days covered by approved leaves; those unpaid (0%); and the share of a day's
    pay lost on the days paid in part (a sick day at 75% loses 0.25)."""
    covered: dict[int, set] = defaultdict(set)
    unpaid: dict[int, set] = defaultdict(set)
    partial: dict[int, Decimal] = defaultdict(Decimal)
    if not ids:
        return covered, unpaid, partial
    kinds = types_by_code(db)
    weekend = policy(db).weekend_days
    q = select(Leave).where(
        Leave.employee_id.in_(ids), Leave.status == "approved", Leave.date_from <= last, Leave.date_to >= first
    )
    for lv in db.scalars(q):
        t = kinds[lv.kind]
        pay = rules.pay_by_day(rules.counted(lv.date_from, lv.date_to, t.counts, weekend), lv.split)
        for d in rules.days(max(lv.date_from, first), min(lv.date_to, last)):
            covered[lv.employee_id].add(d)
            pct = pay.get(d, 100)  # a rest day inside a leave counted in working days: not taken from his pay
            if pct == 0:
                unpaid[lv.employee_id].add(d)
            elif pct < 100:
                partial[lv.employee_id] += Decimal(100 - pct) / 100
    return covered, unpaid, partial
