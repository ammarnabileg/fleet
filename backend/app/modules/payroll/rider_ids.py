"""A platform's driver IDs by month (migration 0076): the ID a platform pays under may be worked by another employee
next month, and the month's pay under it goes to whoever had it that month.

A month with nothing recorded is the latest month before it that has (the office changes only the IDs that moved); a
platform with no month at all is the IDs on the drivers' files. Changing a month records its whole list first, so the
months after it that have nothing of their own follow it. The current month's change is also put on the drivers'
files, which the rest of the system shows."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.modules.audit import service as audit
from app.modules.payroll.models import RiderIdMonth
from app.modules.people import service as people


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def _snapshot_month(db: Session, platform_id: int, month: date) -> date | None:
    return db.scalar(
        select(func.max(RiderIdMonth.month)).where(RiderIdMonth.platform_id == platform_id, RiderIdMonth.month <= month)
    )


def _profile_ids(db: Session, platform_id: int) -> dict[int, str]:
    """The IDs on the drivers' files: the start of a platform with no month recorded."""
    rows = people.platform_profiles(db, platform_id, all_companies=True, company_ids=(), departed=True)
    return {
        p["id"]: p["platform_driver_id"] for p in rows if p["platform_id"] == platform_id and p["platform_driver_id"]
    }


def ids_for(db: Session, platform_id: int, month: date) -> dict[int, str]:
    """{employee id: his driver ID on the platform that month}."""
    at = _snapshot_month(db, platform_id, month)
    if at is None:
        return _profile_ids(db, platform_id)
    q = select(RiderIdMonth.employee_id, RiderIdMonth.rider_id).where(
        RiderIdMonth.platform_id == platform_id, RiderIdMonth.month == at
    )
    found = dict(db.execute(q).all())
    if month >= today().replace(day=1):
        # a driver put on the platform since (his file has an ID no one works this month) works it from now on
        taken = {_norm(v) for v in found.values()}
        for employee_id, rider_id in _profile_ids(db, platform_id).items():
            if employee_id not in found and _norm(rider_id) not in taken:
                found[employee_id] = rider_id
                taken.add(_norm(rider_id))
    return found


def for_employees(db: Session, platform_ids, month: date) -> dict[int, dict[int, str]]:
    """{platform id: {employee id: ID}} for the given platforms that month."""
    return {pid: ids_for(db, pid, month) for pid in {p for p in platform_ids if p is not None}}


BASE = date(2000, 1, 1)  # the files' IDs when the platform's first month was recorded: what every earlier month had


def _materialize(db: Session, platform_id: int, month: date) -> None:
    """The month gets its own list (a copy of the one it was following) before one of its IDs changes. The first
    change on a platform also keeps the files' IDs as they are for the months before it (the files change with it)."""
    if not db.scalar(select(func.count()).where(RiderIdMonth.platform_id == platform_id)):
        for employee_id, rider_id in _profile_ids(db, platform_id).items():
            db.add(RiderIdMonth(platform_id=platform_id, month=BASE, rider_id=rider_id, employee_id=employee_id))
        db.flush()
    have = set(db.scalars(select(RiderIdMonth.employee_id).where(
        RiderIdMonth.platform_id == platform_id, RiderIdMonth.month == month)))  # fmt: skip
    # a month of its own keeps what it has; one following another, or a driver put on the platform since, is added
    for employee_id, rider_id in ids_for(db, platform_id, month).items():
        if employee_id not in have:
            db.add(RiderIdMonth(platform_id=platform_id, month=month, rider_id=rider_id, employee_id=employee_id))
    db.flush()


def month_table(db: Session, platform_id: int, month: date, **scope) -> list[dict]:
    """The platform's drivers in scope with their ID this month and last month (changed: it moved)."""
    from app.modules.payroll.service import add_months

    now, before = ids_for(db, platform_id, month), ids_for(db, platform_id, add_months(month, -1))
    rows = people.platform_profiles(db, platform_id, employee_ids=list(now), **scope)
    out = []
    for p in rows:
        if p["platform_id"] != platform_id and p["id"] not in now:
            continue
        out.append(
            {
                "id": p["public_id"],
                "employee_number": p["employee_number"],
                "name": p["name"],
                "company_id": p["company_id"],
                "rider_id": now.get(p["id"]),
                "previous": before.get(p["id"]),
                "changed": _norm(now.get(p["id"])) != _norm(before.get(p["id"])),
            }
        )
    return out


def set_id(db: Session, platform_id: int, month: date, employee_public_id, *, value: str | None, actor_user_id: int,
           **scope) -> list[dict]:  # fmt: skip
    """The driver works this ID from this month (an empty value: none). An ID another employee had that month moves
    to him; the months after that have their own list keep it."""
    from app.modules.payroll.month import _locked

    e = people.ref_by_public_id(db, employee_public_id, **scope)
    _locked(db, e.company_id, month)
    value = (value or "").strip() or None
    _materialize(db, platform_id, month)
    rows = {r.employee_id: r for r in db.scalars(select(RiderIdMonth).where(
        RiderIdMonth.platform_id == platform_id, RiderIdMonth.month == month).with_for_update())}  # fmt: skip
    before = rows[e.id].rider_id if e.id in rows else None
    holder = next((r for r in rows.values() if value and _norm(r.rider_id) == _norm(value) and r.employee_id != e.id),
                  None)  # fmt: skip
    if holder is not None:
        _locked(db, people.ref(db, holder.employee_id).company_id, month)
        db.delete(holder)
        db.flush()
    if value is None:
        if e.id in rows:
            db.delete(rows[e.id])
    elif e.id in rows:
        rows[e.id].rider_id, rows[e.id].updated_by, rows[e.id].updated_at = value, actor_user_id, func.now()
    else:
        db.add(RiderIdMonth(platform_id=platform_id, month=month, rider_id=value, employee_id=e.id,
                            updated_by=actor_user_id))  # fmt: skip
    db.flush()
    if month == today().replace(day=1):
        _to_files(db, platform_id, e, holder, value, actor_user_id)
    audit.record(
        db,
        action="payroll.rider_id_set",
        entity_type="employee",
        entity_id=e.public_id,
        actor_user_id=actor_user_id,
        company_id=e.company_id,
        before={"platform_id": platform_id, "month": month.isoformat(), "rider_id": before},
        after={"rider_id": value, "taken_from": str(people.ref(db, holder.employee_id).public_id) if holder else None},
    )
    db.commit()
    return month_table(db, platform_id, month, **scope)


def _to_files(db: Session, platform_id: int, e, holder, value, actor_user_id: int) -> None:
    """This month's IDs are also the ones on the drivers' files (the one who lost his ID first, so the file's own
    uniqueness holds)."""
    every = {"all_companies": True, "company_ids": ()}
    if holder is not None:
        h = people.ref(db, holder.employee_id)
        if h.platform_id == platform_id:
            people.put_on_platform(db, h.public_id, platform_id=platform_id, platform_driver_id=None,
                                   actor_user_id=actor_user_id, commit=False, **every)  # fmt: skip
    if e.platform_id == platform_id:
        people.put_on_platform(db, e.public_id, platform_id=platform_id, platform_driver_id=value,
                               actor_user_id=actor_user_id, commit=False, **every)  # fmt: skip
