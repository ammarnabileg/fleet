"""Absence and leave (BRD BR-18, FR-HR-06; FR-PAY-01 "minus the approved absence").

Absence is never recorded on its own (BR-18): a day on which a working driver neither started his day in the app nor
sent a daily report is listed for HR, who marks it: absence, leave, rest day, no vehicle, or a system fault. Each
listed day says whether the driver held a vehicle that day (without one he could not start). Today is not listed
while it is still going on, nor any day before the driver's hire date (or the day his record was made).

A leave covers a range of days: registered, then approved or rejected (with a note), or cancelled (with a reason). An
approved leave covers its days: they are not listed, and a mark on one of them does not count. Two leaves of the
same employee never overlap (pending or approved). Nothing in a month whose payroll is approved can change.

Payroll reads each month's absence days, unpaid leave days, all leave days, and the days still unmarked.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.modules.attendance.models import MARK_KINDS, DayMark, Leave
from app.modules.audit import service as audit
from app.modules.daily_ops import service as daily_ops
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.people import service as people

MAX_LIST_DAYS = 62  # the days to classify, at a time
MAX_LEAVE_DAYS = 120
LIST_LIMIT = 3000


def _span(first: date, last: date, limit: int) -> None:
    if last < first:
        raise AppError(422, "invalid_range")
    if (last - first).days >= limit:
        raise AppError(422, "range_too_long_days", days=limit)


def _days(first: date, last: date):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def _unlocked(db: Session, company_id: int, days: Iterable[date]) -> None:
    """Refuses a change touching a month whose payroll is approved or paid."""
    from app.modules.payroll import service as payroll  # payroll reads this module: imported when used

    for month in sorted({d.replace(day=1) for d in days}):
        if payroll.month_locked(db, company_id, month):
            raise AppError(409, "payroll_locked")


def _scoped(q, column, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(column.in_(list(company_ids)))


# ------------------------------------------------------------------ leaves


def _leave_out(db: Session, rows: list[Leave]) -> list[dict]:
    names = people.names(db, {r.employee_id for r in rows})
    users = identity.user_names(db, {u for r in rows for u in (r.created_by, r.decided_by) if u})
    return [
        {
            "id": str(r.public_id),
            "employee": names.get(r.employee_id),
            "company_id": r.company_id,
            "kind": r.kind,
            "date_from": r.date_from,
            "date_to": r.date_to,
            "days": (r.date_to - r.date_from).days + 1,
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
            "version": r.version,
        }
        for r in rows
    ]


def _get(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Leave:
    q = _scoped(select(Leave).where(Leave.public_id == public_id), Leave.company_id, all_companies, company_ids)
    leave = db.scalar(q.with_for_update() if lock else q)
    if leave is None:
        raise AppError(404, "leave_not_found")
    return leave


def _audit(db: Session, action: str, leave: Leave, *, actor_user_id: int, after: dict | None = None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="leave",
        entity_id=leave.public_id,
        actor_user_id=actor_user_id,
        company_id=leave.company_id,
        after={"kind": leave.kind, "from": leave.date_from, "to": leave.date_to, "status": leave.status}
        | (after or {}),
    )


def create_leave(db: Session, data: dict, *, approve: bool, actor_user_id: int, **scope) -> dict:
    """Registered by the office; approved at once when the user may approve leaves and asks to."""
    employee = people.ref_by_public_id(db, data["employee_id"], **scope)
    first, last = data["date_from"], data["date_to"]
    _span(first, last, MAX_LEAVE_DAYS)
    if data.get("file_sha256"):
        files.get(db, data["file_sha256"])  # a medical certificate, a ticket
    # one registration at a time per employee, so two overlapping leaves cannot both pass the check
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('attendance.leave:' || :e, 0))"), {"e": employee.id})
    clash = db.scalar(
        select(Leave.public_id).where(
            Leave.employee_id == employee.id,
            Leave.status.in_(("pending", "approved")),
            Leave.date_from <= last,
            Leave.date_to >= first,
        )
    )
    if clash is not None:
        raise AppError(409, "leave_overlaps", leave_id=str(clash))
    if approve:
        _unlocked(db, employee.company_id, _days(first, last))
    leave = Leave(
        employee_id=employee.id,
        company_id=employee.company_id,
        kind=data["kind"],
        date_from=first,
        date_to=last,
        note=data.get("note"),
        file_sha256=data.get("file_sha256"),
        created_by=actor_user_id,
        status="approved" if approve else "pending",
        decided_by=actor_user_id if approve else None,
        decided_at=utcnow() if approve else None,
    )
    db.add(leave)
    db.flush()
    _audit(db, "leave.approved" if approve else "leave.registered", leave, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(leave)
    return _leave_out(db, [leave])[0]


def decide_leave(db: Session, public_id, *, approve: bool, note: str | None, actor_user_id: int, **scope) -> dict:
    leave = _get(db, public_id, lock=True, **scope)
    if leave.status != "pending":
        raise AppError(409, "leave_not_pending", status=leave.status)
    if approve:
        _unlocked(db, leave.company_id, _days(leave.date_from, leave.date_to))
    elif not note:
        raise AppError(422, "reason_required")
    leave.status = "approved" if approve else "rejected"
    leave.decided_by, leave.decided_at, leave.decision_note = actor_user_id, utcnow(), note
    leave.version += 1
    _audit(db, f"leave.{leave.status}", leave, actor_user_id=actor_user_id, after={"note": note})
    db.commit()
    return _leave_out(db, [leave])[0]


def cancel_leave(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    leave = _get(db, public_id, lock=True, **scope)
    if leave.status not in ("pending", "approved"):
        raise AppError(409, "leave_not_open", status=leave.status)
    if leave.status == "approved":  # its days counted in an approved payroll stay counted
        _unlocked(db, leave.company_id, _days(leave.date_from, leave.date_to))
    leave.status, leave.cancel_reason = "cancelled", reason
    leave.version += 1
    _audit(db, "leave.cancelled", leave, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _leave_out(db, [leave])[0]


def list_leaves(
    db: Session,
    *,
    status: str | None = None,
    employee_id=None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Leave), Leave.company_id, **scope)
    if status:
        q = q.where(Leave.status.in_(status.split(",")))
    if employee_id is not None:
        q = q.where(Leave.employee_id == people.ref_by_public_id(db, employee_id, **scope).id)
    if date_from is not None:
        q = q.where(Leave.date_to >= date_from)
    if date_to is not None:
        q = q.where(Leave.date_from <= date_to)
    rows = db.scalars(q.order_by(Leave.date_from.desc(), Leave.id.desc()).limit(min(limit, 500)).offset(offset))
    return _leave_out(db, list(rows))


def get_leave(db: Session, public_id, **scope) -> dict:
    return _leave_out(db, [_get(db, public_id, **scope)])[0]


def leave_file(db: Session, public_id, **scope) -> files.FileInfo:
    leave = _get(db, public_id, **scope)
    if leave.file_sha256 is None:
        raise AppError(404, "file_not_found")
    return files.get(db, leave.file_sha256)


def _leave_days(db: Session, ids: list[int], first: date, last: date) -> tuple[dict, dict]:
    """The days covered by approved leaves, each employee's, first to last; and those of unpaid leaves."""
    covered: dict[int, set] = defaultdict(set)
    unpaid: dict[int, set] = defaultdict(set)
    if not ids:
        return covered, unpaid
    q = select(Leave.employee_id, Leave.kind, Leave.date_from, Leave.date_to).where(
        Leave.employee_id.in_(ids), Leave.status == "approved", Leave.date_from <= last, Leave.date_to >= first
    )
    for employee_id, kind, a, b in db.execute(q):
        days = set(_days(max(a, first), min(b, last)))
        covered[employee_id] |= days
        if kind == "unpaid":
            unpaid[employee_id] |= days
    return covered, unpaid


# ------------------------------------------------------------------ the days to classify, and their marks


def _unmarked(db: Session, drivers: list[dict], first: date, last: date) -> list[dict]:
    ids = [d["id"] for d in drivers]
    if not ids or last < first:
        return []
    started = fleet.start_days(db, ids, first, last)
    reported = daily_ops.month_activity(db, ids, first, last)
    held = fleet.held_days(db, ids, first, last)
    marked = set(
        db.execute(
            select(DayMark.employee_id, DayMark.day).where(
                DayMark.employee_id.in_(ids), DayMark.day.between(first, last)
            )
        )
        .tuples()
        .all()
    )
    covered, _ = _leave_days(db, ids, first, last)
    rows = []
    for d in drivers:
        i = d["id"]
        for lo, hi in d["periods"]:
            for day in _days(lo, hi):
                if day in started[i] or day in reported[i]["days"] or (i, day) in marked or day in covered[i]:
                    continue
                rows.append({"driver": d, "day": day, "held_vehicle": day in held[i]})
    return rows


def to_classify(db: Session, *, date_from: date, date_to: date, employee_id=None, **scope) -> dict:
    """The working drivers' days without a start of day or a daily report, unmarked and not on leave (BR-18)."""
    _span(date_from, date_to, MAX_LIST_DAYS)
    last = min(date_to, today() - timedelta(days=1))  # today is still going on
    drivers = people.drivers_at_work(db, date_from, last, public_id=employee_id, **scope)
    rows = _unmarked(db, drivers, date_from, last)
    rows.sort(key=lambda r: (-r["day"].toordinal(), r["driver"]["employee_number"]))
    return {
        "from": date_from,
        "to": last,
        "total": len(rows),
        "days": [
            {
                "employee": {
                    "id": r["driver"]["public_id"],
                    "name": r["driver"]["name"],
                    "employee_number": r["driver"]["employee_number"],
                },
                "day": r["day"],
                "held_vehicle": r["held_vehicle"],
            }
            for r in rows[:LIST_LIMIT]
        ],
    }


def mark_days(db: Session, *, items: list[tuple], kind: str, note: str | None, actor_user_id: int, **scope) -> int:
    """HR's decision on days without a start of day: (employee public id, day) pairs, all of the same kind. A day
    already marked takes the new mark."""
    if kind not in MARK_KINDS:
        raise AppError(422, "invalid_mark")
    by_employee: dict = defaultdict(set)
    for public_id, day in items:
        by_employee[public_id].add(day)
    if any(day > today() for days in by_employee.values() for day in days):
        raise AppError(422, "day_in_future")
    count = 0
    for public_id, days in by_employee.items():
        employee = people.ref_by_public_id(db, public_id, **scope)
        _unlocked(db, employee.company_id, days)
        for day in sorted(days):
            db.execute(
                insert(DayMark)
                .values(employee_id=employee.id, day=day, kind=kind, note=note, marked_by=actor_user_id)
                .on_conflict_do_update(
                    index_elements=[DayMark.employee_id, DayMark.day],
                    set_={"kind": kind, "note": note, "marked_by": actor_user_id, "marked_at": func.now()},
                )
            )
            count += 1
        audit.record(
            db,
            action="attendance.marked",
            entity_type="employee",
            entity_id=employee.public_id,
            actor_user_id=actor_user_id,
            company_id=employee.company_id,
            after={"kind": kind, "days": sorted(days), "note": note},
        )
    db.commit()
    return count


def unmark_day(db: Session, *, employee_id, day: date, actor_user_id: int, **scope) -> None:
    """The mark taken off: the day is listed again."""
    employee = people.ref_by_public_id(db, employee_id, **scope)
    _unlocked(db, employee.company_id, [day])
    gone = db.execute(delete(DayMark).where(DayMark.employee_id == employee.id, DayMark.day == day)).rowcount
    if not gone:
        raise AppError(404, "mark_not_found")
    audit.record(
        db,
        action="attendance.unmarked",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        after={"day": day},
    )
    db.commit()


def list_marks(
    db: Session, *, date_from: date, date_to: date, kind: str | None = None, employee_id=None, **scope
) -> list[dict]:
    """Every mark in the range on someone in scope, a driver who has since left or office staff alike: what payroll
    counts is what HR sees."""
    _span(date_from, date_to, MAX_LIST_DAYS)
    q = select(DayMark).where(DayMark.day.between(date_from, date_to))
    if employee_id is not None:
        q = q.where(DayMark.employee_id == people.ref_by_public_id(db, employee_id, **scope).id)
    if kind:
        q = q.where(DayMark.kind == kind)
    rows = list(db.scalars(q.order_by(DayMark.day.desc(), DayMark.employee_id)))
    who = people.cards(db, {r.employee_id for r in rows}, **scope)
    rows = [r for r in rows if r.employee_id in who]
    users = identity.user_names(db, {r.marked_by for r in rows})
    return [
        {
            "employee": who[r.employee_id],
            "day": r.day,
            "kind": r.kind,
            "note": r.note,
            "marked_by": users.get(r.marked_by),
            "marked_at": r.marked_at,
        }
        for r in rows
    ]


# ------------------------------------------------------------------ for payroll


def month_counts(db: Session, employee_ids: Iterable[int], first: date, last: date) -> dict[int, dict]:
    """Per employee, first to last: the days marked absence (not on an approved leave), the days of unpaid approved
    leaves, every leave day (approved leaves and days marked leave), and the days still to classify (to yesterday)."""
    ids = list(employee_ids)
    out = {i: {"absence_days": 0, "unpaid_leave_days": 0, "leave_days": 0, "unclassified_days": 0} for i in ids}
    if not ids:
        return out
    covered, unpaid = _leave_days(db, ids, first, last)
    q = select(DayMark.employee_id, DayMark.day, DayMark.kind).where(
        DayMark.employee_id.in_(ids), DayMark.day.between(first, last)
    )
    for employee_id, day, kind in db.execute(q):
        if day in covered[employee_id]:
            continue
        if kind == "absence":
            out[employee_id]["absence_days"] += 1
        elif kind == "leave":
            out[employee_id]["leave_days"] += 1
    for i in ids:
        out[i]["leave_days"] += len(covered[i])
        out[i]["unpaid_leave_days"] = len(unpaid[i])
    until = min(last, today() - timedelta(days=1))
    drivers = (
        people.drivers_at_work(db, first, until, all_companies=True, company_ids=(), ids=ids) if until >= first else []
    )
    for r in _unmarked(db, drivers, first, until):
        out[r["driver"]["id"]]["unclassified_days"] += 1
    return out
