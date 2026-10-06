"""Daily reports: each working day the driver sends the number of orders, the cash he collected and a screenshot of
the delivery platform's daily summary (required fields from the settings). The cash becomes a pending collection on
his account at once (the "unapproved" balance); the reviewer approves it as it is, corrects the cash with a reason
(posted adjustment), or rejects the report (the driver sends it again). One live report per driver and day.
"""

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.cash import service as cash
from app.modules.daily_ops.models import Report
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.payroll import service as payroll
from app.modules.people import service as people

MAX_DAYS_BACK = 2  # yesterday's report sent this morning is normal; older ones go through the office


def _out(r: Report, names: dict | None = None, plates: dict | None = None) -> dict:
    return {
        "id": str(r.public_id),
        "driver": (names or {}).get(r.employee_id),
        "company_id": r.company_id,
        "vehicle_plate": (plates or {}).get(r.vehicle_id),
        "business_date": r.business_date,
        "orders_count": r.orders_count,
        "cash_amount": r.cash_amount,
        "approved_cash": r.approved_cash,
        "valid_day": r.valid_day,
        "has_screenshot": r.screenshot_sha256 is not None,
        "notes": r.notes,
        "status": r.status,
        "submitted_at": r.submitted_at,
        "reviewed_at": r.reviewed_at,
        "review_note": r.review_note,
    }


def _many(db: Session, reports: list[Report]) -> list[dict]:
    names = people.names(db, {r.employee_id for r in reports})
    plates = fleet.plate_numbers(db, {r.vehicle_id for r in reports if r.vehicle_id})
    return [_out(r, names, plates) for r in reports]


FIELD = {"orders": "orders_count", "cash": "cash_amount", "valid_day": "valid_day"}


def form(db: Session, driver: people.EmployeeRef) -> dict:
    """What this driver sends: his platform's daily fields (orders and cash for one, orders and whether the platform
    counted the day for another), or without a platform the settings; and whether the screenshot is required."""
    rules = org.get_section(db, "daily_report")
    fields = payroll.daily_fields(db, driver.platform_id)
    if fields is None:
        fields = [f for f, on in (("orders", rules.require_orders_count), ("cash", rules.require_cash)) if on]
    return {"fields": fields, "screenshot": rules.require_screenshot}


def submit(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    driver = people.ref(db, employee_id)
    day = data["business_date"]
    if not today() - timedelta(days=MAX_DAYS_BACK) <= day <= today():
        raise AppError(422, "invalid_business_date")
    asked = form(db, driver)
    for field in [FIELD[f] for f in asked["fields"]] + (["screenshot_sha256"] if asked["screenshot"] else []):
        if data.get(field) is None:
            raise AppError(422, "field_required", field=field)
    if data.get("screenshot_sha256"):
        shot = files.get(db, data["screenshot_sha256"])
        if shot.uploaded_by_device != device_id or shot.content_type not in files.IMAGES:
            raise AppError(422, "file_not_yours")
    custodies = fleet.custodies_for_driver(db, employee_id, utcnow() - timedelta(days=MAX_DAYS_BACK + 1), utcnow())
    custody = custodies[-1] if custodies else None
    amount = Decimal(data.get("cash_amount") or 0)
    report = Report(
        employee_id=employee_id,
        company_id=driver.company_id,
        business_date=day,
        custody_id=custody.id if custody else None,
        vehicle_id=custody.vehicle_id if custody else None,
        orders_count=data.get("orders_count"),
        cash_amount=amount,
        valid_day=data.get("valid_day") if "valid_day" in asked["fields"] else None,
        screenshot_sha256=data.get("screenshot_sha256"),
        notes=data.get("notes"),
        submitted_by_device=device_id,
    )
    try:
        with db.begin_nested():
            db.add(report)
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "reports_one_per_day_idx":
            raise AppError(409, "report_exists") from None
        raise
    db.refresh(report)
    cash.submit_collection(db, driver, report_id=report.id, amount=amount, business_date=day, device_id=device_id)
    cash.check_balance_alert(db, driver)
    audit.record(
        db,
        action="daily_report.submitted",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_type="device",
        company_id=driver.company_id,
        after={"date": day.isoformat(), "orders": report.orders_count, "cash": amount, "valid_day": report.valid_day},
    )
    db.commit()
    return _many(db, [report])[0]


def for_driver(db: Session, employee_id: int, limit: int = 30) -> list[dict]:
    q = select(Report).where(Report.employee_id == employee_id).order_by(Report.business_date.desc(), Report.id.desc())
    return _many(db, list(db.scalars(q.limit(limit))))


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Report.company_id.in_(list(company_ids)))


def list_reports(
    db: Session,
    *,
    status: str | None,
    business_date=None,
    employee_id: int | None = None,
    all_companies: bool,
    company_ids: Iterable[int],
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    q = _scoped(select(Report), all_companies, company_ids)
    if status:
        q = q.where(Report.status == status)
    if business_date:
        q = q.where(Report.business_date == business_date)
    if employee_id:
        q = q.where(Report.employee_id == employee_id)
    q = q.order_by(Report.submitted_at).limit(min(limit, 500)).offset(offset)
    return _many(db, list(db.scalars(q)))


def _row(db: Session, public_id, *, lock: bool = False, all_companies: bool, company_ids) -> Report:
    q = _scoped(select(Report).where(Report.public_id == public_id), all_companies, company_ids)
    report = db.scalar(q.with_for_update() if lock else q)
    if report is None:
        raise AppError(404, "report_not_found")
    return report


def screenshot(db: Session, public_id, **scope) -> files.FileInfo:
    report = _row(db, public_id, **scope)
    if report.screenshot_sha256 is None:
        raise AppError(404, "file_not_found")
    return files.get(db, report.screenshot_sha256)


def approve(
    db: Session, public_id, *, cash_amount: Decimal | None, reason: str | None, actor_user_id: int, **scope
) -> dict:
    report = _row(db, public_id, lock=True, **scope)
    if report.status != "submitted":
        raise AppError(409, "report_not_submitted")
    approved = report.cash_amount if cash_amount is None else cash_amount
    if approved != report.cash_amount and not reason:
        raise AppError(422, "reason_required")  # a correction always says why (spec T-LED-02)
    driver = people.ref(db, report.employee_id)
    cash.approve_collection(
        db,
        driver,
        report_id=report.id,
        reported=report.cash_amount,
        approved=approved,
        reason=reason,
        business_date=report.business_date,
        actor_user_id=actor_user_id,
    )
    report.status, report.approved_cash = "approved", approved
    report.reviewed_by, report.reviewed_at, report.review_note = actor_user_id, utcnow(), reason
    report.version += 1
    notifications.resolve(db, f"daily_report_overdue:{report.id}")
    cash.check_balance_alert(db, driver)
    audit.record(
        db,
        action="daily_report.approved",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_user_id=actor_user_id,
        company_id=report.company_id,
        after={"reported_cash": report.cash_amount, "approved_cash": approved, "reason": reason},
    )
    emit(
        db,
        "daily_report.approved",
        report.public_id,
        {
            "report_id": str(report.public_id),
            "driver_id": str(driver.public_id),
            "business_date": report.business_date.isoformat(),
            "orders": report.orders_count,
            "cash": f"{approved:.3f}",
        },
    )
    db.commit()
    return _many(db, [report])[0]


def reject(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    report = _row(db, public_id, lock=True, **scope)
    if report.status != "submitted":
        raise AppError(409, "report_not_submitted")
    cash.reject_collection(db, report_id=report.id, actor_user_id=actor_user_id)
    report.status, report.review_note = "rejected", reason
    report.reviewed_by, report.reviewed_at = actor_user_id, utcnow()
    report.version += 1
    notifications.resolve(db, f"daily_report_overdue:{report.id}")
    cash.check_balance_alert(db, people.ref(db, report.employee_id))
    audit.record(
        db,
        action="daily_report.rejected",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_user_id=actor_user_id,
        company_id=report.company_id,
        after={"reason": reason},
    )
    db.commit()
    return _many(db, [report])[0]


def scan_overdue(db: Session) -> int:
    """Hourly: a report waiting longer than the review limit alerts the reviewers (escalation, spec 13)."""
    hours = org.get_section(db, "cash").report_review_hours
    late = db.scalars(
        select(Report).where(Report.status == "submitted", Report.submitted_at < utcnow() - timedelta(hours=hours))
    )
    raised = 0
    for report in late:
        driver = people.ref(db, report.employee_id)
        raised += notifications.raise_alert(
            db,
            "daily_report_overdue",
            company_id=report.company_id,
            entity_type="daily_report",
            entity_id=report.public_id,
            params={"driver": driver.name, "date": report.business_date.isoformat(), "hours": hours},
            dedupe_key=f"daily_report_overdue:{report.id}",
        )
    db.commit()
    return raised


def month_activity(db: Session, employee_ids: Iterable[int], first, last) -> dict[int, dict]:
    """For payroll, per driver, first to last inclusive: the days he sent a daily report (not rejected), and in his
    approved reports the orders and the days the platform counted (valid_day); and how many still wait for review
    (their figures count only once approved)."""
    ids = list(employee_ids)
    out = {i: {"days": set(), "orders": 0, "valid_days": 0, "pending": 0} for i in ids}
    if not ids:
        return out
    q = select(Report.employee_id, Report.business_date, Report.orders_count, Report.valid_day, Report.status).where(
        Report.employee_id.in_(ids), Report.business_date.between(first, last), Report.status != "rejected"
    )
    for employee_id, day, orders, valid, status in db.execute(q):
        row = out[employee_id]
        row["days"].add(day)
        if status == "approved":
            row["orders"] += orders or 0
            row["valid_days"] += bool(valid)
        else:
            row["pending"] += 1
    return out
