"""Absence and leave (BRD BR-18, FR-HR-06; FR-PAY-01 "minus the approved absence").

Absence is never recorded on its own (BR-18): a day on which a working driver neither started his day in the app nor
sent a daily report is listed for HR, who marks it: absence, leave, rest day, no vehicle, or a system fault. Each
listed day says whether the driver held a vehicle that day (without one he could not start). Today is not listed
while it is still going on, nor any day before the driver's hire date (or the day his record was made).

A leave covers a range of days: registered, then approved or rejected (with a note), or cancelled (with a reason). An
approved leave covers its days: they are not listed, and a mark on one of them does not count. Two leaves of the
same employee never overlap (pending or approved). Nothing in a month whose payroll is approved can change.

Payroll reads each month's absence days, unpaid leave days, the share of pay lost on leave days paid in part, all leave
days, and the days still unmarked.

Absence without permission (غياب بدون إذن) is never a request: it is the office's mark. Labour law Art. 41: more than
7 consecutive days, or more than 20 days in a year, without a legitimate reason may justify dismissal without
indemnity; marking such days raises an office alert to review the legal procedure (prior warning). Nothing is ever
done automatically. The thresholds are in the leaves settings.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError
from app.modules.attendance import leaves
from app.modules.attendance.models import MARK_KINDS, DayMark
from app.modules.audit import service as audit
from app.modules.daily_ops import service as daily_ops
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.people import service as people

MAX_LIST_DAYS = 62  # the days to classify, at a time
LIST_LIMIT = 3000

# the leaves and absence requests, with their types and rules (leaves.py)
_span, _unlocked, _scoped = leaves.span, leaves.unlocked, leaves.scoped
list_types, update_type, preview, create_leave = (
    leaves.list_types,
    leaves.update_type,
    leaves.preview,
    leaves.create_leave,
)
decide_leave, cancel_leave, list_leaves = leaves.decide_leave, leaves.cancel_leave, leaves.list_leaves
set_followup_from, mark_followed_up, scan_followups = (
    leaves.set_followup_from,
    leaves.mark_followed_up,
    leaves.scan_followups,
)
employee_balances, pending_count = leaves.employee_balances, leaves.pending_count
driver_view, driver_preview, driver_request, driver_cancel = (
    leaves.driver_view,
    leaves.driver_preview,
    leaves.driver_request,
    leaves.driver_cancel,
)


def _days(first: date, last: date):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def get_leave(db: Session, public_id, **scope) -> dict:
    return leaves.leave_out(db, [leaves.get_row(db, public_id, **scope)])[0]


def leave_file(db: Session, public_id, **scope) -> files.FileInfo:
    leave = leaves.get_row(db, public_id, **scope)
    if leave.file_sha256 is None:
        raise AppError(404, "file_not_found")
    return files.get(db, leave.file_sha256)


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
    covered, _, _ = leaves.leave_days(db, ids, first, last)
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
        if kind == "absence":
            _art41(db, employee, days)
    db.commit()
    return count


def _absences(db: Session, employee_id: int, first: date, last: date) -> set[date]:
    """His days marked absence first..last, less those an approved leave covers."""
    marked = set(
        db.scalars(
            select(DayMark.day).where(
                DayMark.employee_id == employee_id, DayMark.kind == "absence", DayMark.day.between(first, last)
            )
        )
    )
    covered, _, _ = leaves.leave_days(db, [employee_id], first, last)
    return marked - covered[employee_id]


def _art41(db: Session, employee, days: Iterable[date]) -> None:
    """Art. 41 thresholds: an alert (once per run of days, and once per year) for the office to review the legal
    procedure. Never an action."""
    p = leaves.policy(db)
    for year in sorted({d.year for d in days}):
        absent = _absences(db, employee.id, date(year, 1, 1), date(year, 12, 31))
        if len(absent) > p.absence_alert_year_days:
            notifications.raise_alert(
                db,
                "absence_yearly",
                company_id=employee.company_id,
                entity_type="employee",
                entity_id=employee.public_id,
                params={"driver": employee.name, "days": len(absent), "year": year},
                dedupe_key=f"absence_yearly:{employee.id}:{year}",
                once=True,
            )
    lo, hi = min(days) - timedelta(days=60), max(days) + timedelta(days=60)
    absent = _absences(db, employee.id, lo, hi)
    for d in sorted(set(days) & absent):
        start = d
        while start - timedelta(days=1) in absent:
            start -= timedelta(days=1)
        end = d
        while end + timedelta(days=1) in absent:
            end += timedelta(days=1)
        run = (end - start).days + 1
        if run > p.absence_alert_consecutive_days:
            notifications.raise_alert(
                db,
                "absence_consecutive",
                company_id=employee.company_id,
                entity_type="employee",
                entity_id=employee.public_id,
                params={"driver": employee.name, "days": run, "from": start.isoformat(), "to": end.isoformat()},
                dedupe_key=f"absence_consecutive:{employee.id}:{start}",
                refresh=True,
            )


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
    out = {
        i: {
            "absence_days": 0,
            "unpaid_leave_days": 0,
            "leave_part_unpaid": Decimal(0),
            "leave_days": 0,
            "unclassified_days": 0,
        }
        for i in ids
    }
    if not ids:
        return out
    covered, unpaid, partial = leaves.leave_days(db, ids, first, last)
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
        out[i]["leave_part_unpaid"] = partial[i]  # a day's pay lost in part (sick days at 75%, 50%, 25%)
    until = min(last, today() - timedelta(days=1))
    drivers = (
        people.drivers_at_work(db, first, until, all_companies=True, company_ids=(), ids=ids) if until >= first else []
    )
    for r in _unmarked(db, drivers, first, until):
        out[r["driver"]["id"]]["unclassified_days"] += 1
    return out
