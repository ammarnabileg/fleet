"""The records behind a dashboard figure that no list page filters by itself: a click on the figure lists exactly
what it counts, by the same conditions (BRD FR-DSH: every figure explains itself). The other figures open their own
pages, filtered."""

from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.modules.cash.models import Receipt
from app.modules.daily_ops.models import Report
from app.modules.fleet.models import Custody, OdometerReading, Vehicle
from app.modules.org import service as org
from app.modules.people.models import Employee, EmploymentStatus
from app.modules.reports import service as base
from app.modules.tracking.models import LastPosition

LIMIT = 500

# metric: the permissions any one of which shows its figure on the dashboard
METRICS: dict[str, tuple[str, ...]] = {
    "signal_lost": ("tracking.live",),
    "without_vehicle": ("custody.view", "tracking.live"),
    "started_today": ("custody.view", "tracking.live"),
    "reports_today": ("daily_reports.view",),
    "today_missing": ("daily_reports.view",),
    "reports_overdue": ("daily_reports.view",),
    "deposited_today": ("cash.view",),
}


def _money(value) -> str | None:
    return None if value is None else f"{value:.3f}"


def _person(public_id, name) -> dict:
    return {"id": str(public_id), "name": name}


def details(
    db: Session, metric: str, *, permissions: frozenset[str], all_companies: bool, company_ids: Iterable[int]
) -> dict:
    if not any(p in permissions for p in METRICS[metric]):
        raise AppError(403, "permission_denied", permission=METRICS[metric][0])
    company_ids = list(company_ids)
    rows = LISTS[metric](db, all_companies, company_ids)
    return {"metric": metric, "as_of": utcnow(), "count": len(rows), "rows": rows[:LIMIT]}


def _signal_lost(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    """The custodies open now whose last point (or start, with none yet) is older than the configured minutes."""
    lost_after = timedelta(minutes=org.get_section(db, "tracking").signal_loss_minutes)
    own_point = LastPosition.custody_id == Custody.id
    reference = func.coalesce(case((own_point, LastPosition.recorded_at)), Custody.started_at)
    q = (
        select(Custody.public_id, Custody.started_at, Vehicle.public_id, Vehicle.plate_number, Employee.public_id,
               Employee.name, reference.label("last_seen"),
               case((own_point, True), else_=False).label("has_point"))
        .select_from(Custody)
        .join(Vehicle, Vehicle.id == Custody.vehicle_id)
        .join(Employee, Employee.id == Custody.driver_id)
        .outerjoin(LastPosition, LastPosition.vehicle_id == Custody.vehicle_id)
        .where(
            Custody.ended_at.is_(None),
            base._in_scope(Custody.company_id, all_companies, company_ids),
            reference < utcnow() - lost_after,
        )
        .order_by(reference)
    )  # fmt: skip
    return [
        {
            "custody_id": str(cid),
            "started_at": started,
            "vehicle": {"id": str(vid), "plate": plate},
            "driver": _person(eid, name),
            "last_seen": last,
            "has_point": bool(point),
        }
        for cid, started, vid, plate, eid, name, last, point in db.execute(q)
    ]


def _without_vehicle(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    """The drivers at work (a working status) who hold no vehicle now."""
    q = (
        select(Employee.public_id, Employee.name, Employee.employee_number, Employee.company_id, EmploymentStatus.name)
        .join(EmploymentStatus, EmploymentStatus.code == Employee.status_code)
        .where(
            Employee.is_driver.is_(True),
            EmploymentStatus.is_terminal.is_(False),
            EmploymentStatus.is_working.is_(True),
            Employee.id.not_in(select(Custody.driver_id).where(Custody.ended_at.is_(None))),
            base._in_scope(Employee.company_id, all_companies, company_ids),
        )
        .order_by(Employee.employee_number)
    )
    return [
        {"driver": _person(p, n), "employee_number": num, "company_id": c, "status": s}
        for p, n, num, c, s in db.execute(q)
    ]


def _readings_today(db: Session, all_companies: bool, company_ids: list[int]) -> dict[int, tuple]:
    """Each driver's first start-of-day reading today: when, which vehicle, what km."""
    ids = base._started_today(db, all_companies, company_ids)
    if not ids:
        return {}
    q = (
        select(OdometerReading.driver_id, OdometerReading.recorded_at, OdometerReading.value_km, Vehicle.public_id,
               Vehicle.plate_number)
        .join(Vehicle, Vehicle.id == OdometerReading.vehicle_id)
        .where(OdometerReading.kind == "start_day", OdometerReading.business_date == today(),
               OdometerReading.driver_id.in_(ids))
        .order_by(OdometerReading.recorded_at.desc())
    )  # fmt: skip
    return {d: (at, km, vid, plate) for d, at, km, vid, plate in db.execute(q)}  # the earliest one wins


def _drivers(db: Session, ids: Iterable[int]) -> dict[int, tuple]:
    return {i: (p, n, num) for i, p, n, num in db.execute(
        select(Employee.id, Employee.public_id, Employee.name, Employee.employee_number).where(Employee.id.in_(ids))
    )}  # fmt: skip


def _started_today_rows(readings: dict, drivers: dict) -> list[dict]:
    rows = []
    for driver_id, (at, km, vid, plate) in sorted(readings.items(), key=lambda x: x[1][0]):
        p, n, num = drivers[driver_id]
        rows.append({"driver": _person(p, n), "employee_number": num, "at": at, "km": km,
                     "vehicle": {"id": str(vid), "plate": plate}})  # fmt: skip
    return rows


def _started(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    readings = _readings_today(db, all_companies, company_ids)
    return _started_today_rows(readings, _drivers(db, readings))


def _today_missing(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    """Started the day (a start-of-day reading today), no report sent for today yet (or only rejected ones)."""
    readings = _readings_today(db, all_companies, company_ids)
    reported = set(
        db.scalars(
            select(Report.employee_id).where(
                base._in_scope(Report.company_id, all_companies, company_ids),
                Report.business_date == today(),
                Report.status != "rejected",
            )
        )
    )
    missing = {d: r for d, r in readings.items() if d not in reported}
    return _started_today_rows(missing, _drivers(db, missing))


def _reports_overdue(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    """Sent and waiting for review longer than the hours set in the cash settings."""
    hours = org.get_section(db, "cash").report_review_hours
    q = (
        select(Report.public_id, Report.business_date, Report.submitted_at, Report.orders_count, Report.cash_amount,
               Employee.public_id, Employee.name)
        .join(Employee, Employee.id == Report.employee_id)
        .where(
            base._in_scope(Report.company_id, all_companies, company_ids),
            Report.status == "submitted",
            Report.submitted_at < utcnow() - timedelta(hours=hours),
        )
        .order_by(Report.submitted_at)
    )  # fmt: skip
    return [
        {"report_id": str(rid), "business_date": day, "submitted_at": at, "orders": orders, "cash": _money(cash),
         "driver": _person(p, n), "hours": hours}
        for rid, day, at, orders, cash, p, n in db.execute(q)
    ]  # fmt: skip


def _reports_today(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    """Today's reports not rejected, as today's figures count them (sent, approved, orders, cash)."""
    q = (
        select(Report.public_id, Report.status, Report.orders_count, Report.cash_amount, Report.submitted_at,
               Employee.public_id, Employee.name)
        .join(Employee, Employee.id == Report.employee_id)
        .where(
            base._in_scope(Report.company_id, all_companies, company_ids),
            Report.business_date == today(),
            Report.status != "rejected",
        )
        .order_by(Report.submitted_at.desc())
    )  # fmt: skip
    return [
        {"report_id": str(rid), "status": status, "orders": orders, "cash": _money(cash), "submitted_at": at,
         "driver": _person(p, n)}
        for rid, status, orders, cash, at, p, n in db.execute(q)
    ]  # fmt: skip


def _deposited_today(db: Session, all_companies: bool, company_ids: list[int]) -> list[dict]:
    """The receipts given today (Kuwait day): who handed in how much."""
    q = (
        select(Receipt.public_id, Receipt.receipt_no, Receipt.amount, Receipt.created_at, Employee.public_id,
               Employee.name, Receipt.driver_confirmed_at)
        .join(Employee, Employee.id == Receipt.driver_id)
        .where(
            base._in_scope(Employee.company_id, all_companies, company_ids),
            func.date(func.timezone("Asia/Kuwait", Receipt.created_at)) == today(),
        )
        .order_by(Receipt.created_at.desc())
    )  # fmt: skip
    return [
        {"receipt_id": str(rid), "receipt_no": no, "amount": f"{amount:.3f}", "at": at, "driver": _person(p, n),
         "confirmed": confirmed is not None}
        for rid, no, amount, at, p, n, confirmed in db.execute(q)
    ]  # fmt: skip


LISTS = {
    "signal_lost": _signal_lost,
    "without_vehicle": _without_vehicle,
    "started_today": _started,
    "reports_today": _reports_today,
    "today_missing": _today_missing,
    "reports_overdue": _reports_overdue,
    "deposited_today": _deposited_today,
}
