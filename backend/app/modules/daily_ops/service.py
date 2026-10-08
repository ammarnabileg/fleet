"""Daily reports: each working day the driver sends the number of orders, the cash he collected and a screenshot of
the delivery platform's daily summary (required fields from the settings). The cash becomes a pending collection on
his account at once (the "unapproved" balance); the reviewer approves it as it is, corrects the cash with a reason
(posted adjustment), or rejects the report (the driver sends it again). One live report per driver and work
session: a driver who starts again after ending the day sends the new session's report, and the day's figures are
the sum of its reports.
"""

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import business_date, today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.cash import service as cash
from app.modules.daily_ops.models import Report, ReportChange
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.i18n import service as i18n
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.payroll import service as payroll
from app.modules.people import service as people

MAX_DAYS_BACK = 2  # yesterday's report sent this morning is normal; older ones go through the office


def _out(r: Report, names: dict | None = None, plates: dict | None = None) -> dict:
    return {
        "late": business_date(r.submitted_at) > r.business_date,  # sent after its own day (BRD BR-04)
        "deviations": [],  # in the reviewers' list: what is far from the driver's average
        "id": str(r.public_id),
        "driver": (names or {}).get(r.employee_id),
        "company_id": r.company_id,
        "vehicle_plate": (plates or {}).get(r.vehicle_id),
        "business_date": r.business_date,
        "session": r.session,
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
    waiting = set(
        db.scalars(
            select(ReportChange.report_id).where(
                ReportChange.report_id.in_([r.id for r in reports]), ReportChange.status == "pending"
            )
        )
    )
    return [_out(r, names, plates) | {"change_pending": r.id in waiting} for r in reports]


FIELD = {"orders": "orders_count", "cash": "cash_amount", "valid_day": "valid_day"}


def form(db: Session, driver: people.EmployeeRef) -> dict:
    """What this driver sends: his platform's daily fields (orders and cash for one, orders and whether the platform
    counted the day for another), or without a platform the settings; and whether the screenshot is required."""
    rules = org.get_section(db, "daily_report")
    fields = payroll.daily_fields(db, driver.platform_id)
    if fields is None:
        fields = [f for f, on in (("orders", rules.require_orders_count), ("cash", rules.require_cash)) if on]
    return {"fields": fields, "screenshot": rules.require_screenshot, "end_reading": rules.require_end_reading}


def _validate(db: Session, driver: people.EmployeeRef, device_id: int, data: dict, new_shot: bool = True) -> dict:
    """What the driver's platform asks is there; a screenshot is his own phone's upload."""
    asked = form(db, driver)
    for field in [FIELD[f] for f in asked["fields"]] + (["screenshot_sha256"] if asked["screenshot"] else []):
        if data.get(field) is None:
            raise AppError(422, "field_required", field=field)
    if new_shot and data.get("screenshot_sha256"):
        shot = files.get(db, data["screenshot_sha256"])
        if shot.uploaded_by_device != device_id or shot.content_type not in files.IMAGES:
            raise AppError(422, "file_not_yours")
    return asked


def submit(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    driver = people.ref(db, employee_id)
    day = data["business_date"]
    if not today() - timedelta(days=MAX_DAYS_BACK) <= day <= today():
        raise AppError(422, "invalid_business_date")
    asked = _validate(db, driver, device_id, data)
    started = fleet.driver_days(db, employee_id, day, day).get(day)
    # The session the driver wrote it for (the app fixes it when he fills the form), so a retry or a report that
    # arrives after his next start stays in its own session; an older app sends none: the sessions known now.
    # Sent again for the same session, it is that session's report (report_exists).
    known = max(1, len(started["sessions"]) if started else 0)
    session = data.get("session") or known
    if session > known:
        raise AppError(422, "invalid_session")  # a session the server has not seen started
    if asked["end_reading"] and day == today() and started is not None:
        # drove today and this session is still open: its closing reading comes first
        if started["end"] is None and session == len(started["sessions"]):
            raise AppError(409, "end_reading_required")
    custodies = fleet.custodies_for_driver(db, employee_id, utcnow() - timedelta(days=MAX_DAYS_BACK + 1), utcnow())
    custody = custodies[-1] if custodies else None
    amount = Decimal(data.get("cash_amount") or 0)
    report = Report(
        employee_id=employee_id,
        company_id=driver.company_id,
        business_date=day,
        session=session,
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
        if violated_constraint(exc) == "reports_one_per_session_idx":
            existing = db.scalar(
                select(Report.public_id).where(
                    Report.employee_id == employee_id,
                    Report.business_date == day,
                    Report.session == session,
                    Report.status != "rejected",
                )
            )
            raise AppError(409, "report_exists", report_id=str(existing)) from None  # edit that one (UAT-04)
        raise
    db.refresh(report)
    cash.submit_collection(db, driver, report_id=report.id, amount=amount, business_date=day, device_id=device_id)
    notifications.resolve(db, f"daily_report_missing:{employee_id}:{day}")  # sent after all
    cash.check_balance_alert(db, driver)
    approvals.submitted(db, "daily_report", **_approval(db, report, driver))
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
    reports = list(db.scalars(q))
    out = _many(db, reports)
    if reports:
        percent = org.get_section(db, "daily_report").deviation_percent
        history = _history(
            db,
            {r.employee_id for r in reports},
            min(r.business_date for r in reports) - timedelta(days=AVERAGE_DAYS),
            max(r.business_date for r in reports),
        )
        totals = _day_totals(db, reports)
        for report, row in zip(reports, out, strict=True):
            row["deviations"] = _deviations(
                totals[report.id],
                _average(history[report.employee_id], report.business_date),
                percent,
            )
    return out


AVERAGE_DAYS = 30  # the driver's average over his approved reports of the 30 days before (FR-DWR-05)
MIN_HISTORY = 5  # fewer approved days than this: no average to compare with


def _history(db: Session, employee_ids: set[int], first, last) -> dict[int, list[tuple]]:
    """The approved reports of these drivers between the two days, a day's sessions added up: (day, orders, cash as
    approved)."""
    out: dict[int, list[tuple]] = {i: [] for i in employee_ids}
    rows = db.execute(
        select(
            Report.employee_id,
            Report.business_date,
            func.sum(Report.orders_count),
            func.sum(func.coalesce(Report.approved_cash, Report.cash_amount)),
        )
        .where(
            Report.employee_id.in_(employee_ids),
            Report.status == "approved",
            Report.business_date.between(first, last),
        )
        .group_by(Report.employee_id, Report.business_date)
    )
    for employee_id, day, orders, amount in rows:
        out[employee_id].append((day, orders, amount))
    return out


def _average(rows: list[tuple], day) -> dict:
    window = [r for r in rows if day - timedelta(days=AVERAGE_DAYS) <= r[0] < day]
    orders = [r[1] for r in window if r[1] is not None]
    return {
        "days": len(window),
        "orders": round(Decimal(sum(orders)) / len(orders), 1) if orders else None,
        "cash": (sum(r[2] for r in window) / len(window)).quantize(Decimal("0.001")) if window else None,
    }


def _day_totals(db: Session, reports: list[Report]) -> dict[int, tuple]:
    """The live reports of each of these drivers' days added up, (orders, cash): a day with two work sessions is
    judged as a day, not each half on its own."""
    keys = {(r.employee_id, r.business_date) for r in reports}
    rows = db.execute(
        select(Report.employee_id, Report.business_date, func.sum(Report.orders_count), func.sum(Report.cash_amount))
        .where(tuple_(Report.employee_id, Report.business_date).in_(keys), Report.status != "rejected")
        .group_by(Report.employee_id, Report.business_date)
    )
    days = {(e, d): (o, c) for e, d, o, c in rows}
    # a rejected report is judged on its own (also one rejected meanwhile, no longer in the day's total)
    return {
        r.id: (r.orders_count, r.cash_amount)
        if r.status == "rejected"
        else days.get((r.employee_id, r.business_date), (r.orders_count, r.cash_amount))
        for r in reports
    }


def _deviations(day: tuple, average: dict, percent: int) -> list[str]:
    """The day's orders or cash further from the driver's own average than the set percent, either way
    (FR-DWR-08)."""
    if average["days"] < MIN_HISTORY:
        return []
    out = []
    for field, value in zip(("orders", "cash"), day, strict=True):
        mean = average[field]
        if value is not None and mean and abs(Decimal(value) - mean) * 100 > mean * percent:
            out.append(field)
    return out


def evidence(db: Session, public_id, **scope) -> dict:
    """What the reviewer checks the report against (FR-DWR-05): the day's odometer readings, start and close, and the
    distance; the driver's averages over the 30 days before; what deviates from them."""
    report = _row(db, public_id, **scope)
    day = report.business_date
    days = fleet.driver_days(db, report.employee_id, day - timedelta(days=AVERAGE_DAYS), day)
    average = _average(
        _history(db, {report.employee_id}, day - timedelta(days=AVERAGE_DAYS), day)[report.employee_id], day
    )
    kms = [d["km"] for d_day, d in days.items() if d_day < day and d["km"] is not None]
    this = days.get(day)
    sessions = this["sessions"] if this else []
    # the sessions this report covers: after the day's previous live report, up to its own session
    previous = db.scalar(
        select(func.max(Report.session)).where(
            Report.employee_id == report.employee_id,
            Report.business_date == day,
            Report.status != "rejected",
            Report.session < report.session,
        )
    )
    span = sessions[(previous or 0) : report.session] or sessions[-1:]
    closed = [x["km"] for x in span if x["km"] is not None]
    return {
        "start": span[0]["start"] if span else None,
        "end": span[-1]["end"] if span else None,
        "km": sum(closed) if closed else None,
        "day_km": this["km"] if this else None,
        "sessions": len(sessions),
        "average": average | {"km": round(sum(kms) / len(kms)) if kms else None, "km_days": len(kms)},
        "deviations": _deviations(
            _day_totals(db, [report])[report.id],
            average,
            org.get_section(db, "daily_report").deviation_percent,
        ),
    }


def odometer_photo(db: Session, public_id, which: str, **scope) -> files.FileInfo:
    reading = evidence(db, public_id, **scope)[which]
    if reading is None:
        raise AppError(404, "file_not_found")
    return files.get(db, reading["photo_sha256"])


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


def _approval(db: Session, report: Report, driver: people.EmployeeRef) -> dict:
    lang = i18n.default_language(db).code  # the name as text: the inbox shows it as typed, not as a dict
    return {
        "document_id": report.id,
        "document_key": report.public_id,
        "document_ref": f"{i18n.pick(driver.name, lang, lang)} {report.business_date.isoformat()}"
        + (f" #{report.session}" if report.session > 1 else ""),
        "company_id": report.company_id,
        "amount": report.cash_amount,
    }


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
    if not approvals.gate(
        db, "daily_report", **_approval(db, report, driver), actor_user_id=actor_user_id, reason=reason
    ):
        if approved != report.cash_amount:
            raise AppError(409, "correction_at_last_step")  # the cash is corrected by whoever approves it last
        db.commit()
        return _many(db, [report])[0]
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
    if approved != report.cash_amount:  # the driver learns his cash was corrected, and why
        notifications.notify_driver(
            db,
            report.employee_id,
            "report_corrected",
            params={
                "date": report.business_date.isoformat(),
                "reported": f"{report.cash_amount:.3f}",
                "approved": f"{approved:.3f}",
                "reason": reason,
            },
            entity_type="daily_report",
            entity_id=report.public_id,
        )
    notifications.resolve(db, f"daily_report_overdue:{report.id}")
    notifications.resolve(db, f"daily_report_escalated:{report.id}")
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
    driver = people.ref(db, report.employee_id)
    approvals.gate(
        db, "daily_report", **_approval(db, report, driver), actor_user_id=actor_user_id, approve=False, reason=reason
    )
    cash.reject_collection(db, report_id=report.id, actor_user_id=actor_user_id)
    report.status, report.review_note = "rejected", reason
    report.reviewed_by, report.reviewed_at = actor_user_id, utcnow()
    report.version += 1
    notifications.notify_driver(
        db,
        report.employee_id,
        "report_rejected",
        params={"date": report.business_date.isoformat(), "reason": reason},
        entity_type="daily_report",
        entity_id=report.public_id,
    )
    notifications.resolve(db, f"daily_report_overdue:{report.id}")
    notifications.resolve(db, f"daily_report_escalated:{report.id}")
    cash.check_balance_alert(db, driver)
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


def scan_missing(db: Session, day=None) -> int:
    """At the end of the day: the drivers who started it and sent no report, or started again and sent none for the
    last session, are named to the supervisors, and the driver is reminded in the app (BRD FR-DWR-07). Sending it
    closes the alert."""
    day = day or today()
    started = fleet.drivers_started(db, day)
    sent = dict(
        db.execute(
            select(Report.employee_id, func.max(Report.session))
            .where(Report.business_date == day)
            .group_by(Report.employee_id)
        ).all()
    )
    raised = 0
    for employee_id in sorted(e for e, sessions in started.items() if sent.get(e, 0) < sessions):
        driver = people.ref(db, employee_id)
        raised += notifications.raise_alert(
            db,
            "daily_report_missing",
            company_id=driver.company_id,
            entity_type="employee",
            entity_id=driver.public_id,
            params={"driver": driver.name, "date": day.isoformat()},
            dedupe_key=f"daily_report_missing:{employee_id}:{day}",
        )
        notifications.notify_driver(
            db, employee_id, "report_missing", params={"date": day.isoformat()}, dedupe_key=f"report_missing:{day}"
        )
    db.commit()
    return raised


def scan_overdue(db: Session) -> int:
    """Hourly: a report waiting longer than the review limit alerts the reviewers, and is escalated to the manager
    (BRD BR-05, spec 13)."""
    hours = org.get_section(db, "cash").report_review_hours
    late = db.scalars(
        select(Report).where(
            Report.status == "submitted",
            func.coalesce(Report.updated_at, Report.submitted_at) < utcnow() - timedelta(hours=hours),
        )
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
        notifications.raise_alert(
            db,
            "daily_report_escalated",
            company_id=report.company_id,
            entity_type="daily_report",
            entity_id=report.public_id,
            params={"driver": driver.name, "date": report.business_date.isoformat(), "hours": hours},
            dedupe_key=f"daily_report_escalated:{report.id}",
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
    valid_days: dict[int, set] = {i: set() for i in ids}  # a day with several sessions counts once
    q = select(Report.employee_id, Report.business_date, Report.orders_count, Report.valid_day, Report.status).where(
        Report.employee_id.in_(ids), Report.business_date.between(first, last), Report.status != "rejected"
    )
    for employee_id, day, orders, valid, status in db.execute(q):
        row = out[employee_id]
        row["days"].add(day)
        if status == "approved":
            row["orders"] += orders or 0  # the sessions' orders add up
            if valid:
                valid_days[employee_id].add(day)
        else:
            row["pending"] += 1
    for employee_id, days in valid_days.items():
        out[employee_id]["valid_days"] = len(days)
    return out


# ------------------------------------------------------------------ changes (BRD FR-DWR-04, FR-DWR-06, BR-06, UAT-04)

EDITABLE = ("orders_count", "cash_amount", "valid_day", "screenshot_sha256", "notes")


def _values(r: Report, approved: bool = False) -> dict:
    amount = r.approved_cash if approved and r.approved_cash is not None else r.cash_amount
    return {
        "orders_count": r.orders_count,
        "cash_amount": f"{amount:.3f}",
        "valid_day": r.valid_day,
        "screenshot_sha256": r.screenshot_sha256,
        "notes": r.notes,
    }


def _wanted(report: Report, data: dict, approved: bool = False) -> tuple[dict, dict, dict]:
    """The fields the driver changes: (merged values, what they were, what they become); after approval the cash
    compared is the approved one."""
    current = _values(report, approved)
    asked = {k: (f"{Decimal(v):.3f}" if k == "cash_amount" and v is not None else v) for k, v in data.items()}
    changed = {k: v for k, v in asked.items() if k in EDITABLE and v != current[k]}
    return current | changed, {k: current[k] for k in changed}, changed


def _drivers_report(db: Session, employee_id: int, public_id) -> Report:
    report = db.scalar(
        select(Report).where(Report.public_id == public_id, Report.employee_id == employee_id).with_for_update()
    )
    if report is None:
        raise AppError(404, "report_not_found")
    return report


def _log(db: Session, report: Report, kind: str, status: str, before: dict, after: dict, **extra) -> ReportChange:
    change = ReportChange(report_id=report.id, kind=kind, status=status, before=before, after=after, **extra)
    db.add(change)
    db.flush()
    return change


def edit(db: Session, *, employee_id: int, device_id: int, public_id, data: dict) -> dict:
    """The driver corrects his report until it is approved; one sent back to him goes to review again. A cash change
    replaces the pending collection, so the ledger only ever holds what was finally reported."""
    report = _drivers_report(db, employee_id, public_id)
    if report.status not in ("submitted", "returned"):
        raise AppError(409, "report_not_editable", status=report.status)
    driver = people.ref(db, employee_id)
    merged, before, after = _wanted(report, data)
    _validate(db, driver, device_id, merged, new_shot="screenshot_sha256" in after)
    returned = report.status == "returned"
    if not after and not returned:
        return _many(db, [report])[0]
    for field, value in after.items():
        setattr(report, field, Decimal(value) if field == "cash_amount" else value)
    if "cash_amount" in after:
        cash.replace_collection(
            db,
            driver,
            report_id=report.id,
            amount=report.cash_amount,
            business_date=report.business_date,
            device_id=device_id,
        )
    report.status, report.updated_at, report.version = "submitted", utcnow(), report.version + 1
    _log(db, report, "edit", "applied", before, after, created_by_device=device_id)
    if returned or "cash_amount" in after:  # sent back to review, or another amount: the approval starts over
        approvals.submitted(db, "daily_report", **_approval(db, report, driver), note="edited")
    cash.check_balance_alert(db, driver)
    audit.record(
        db,
        action="daily_report.edited",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_type="device",
        company_id=report.company_id,
        before=before,
        after=after,
    )
    db.commit()
    return _many(db, [report])[0]


def send_back(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """The reviewer asks the driver to correct his report (FR-DWR-04), with the reason he reads in the app."""
    report = _row(db, public_id, lock=True, **scope)
    if report.status != "submitted":
        raise AppError(409, "report_not_submitted")
    report.status, report.review_note, report.version = "returned", reason, report.version + 1
    _log(db, report, "returned", "applied", {}, {}, reason=reason, created_by=actor_user_id)
    approvals.withdrawn(db, "daily_report", [report.id], note="returned")
    notifications.notify_driver(
        db,
        report.employee_id,
        "report_returned",
        params={"date": report.business_date.isoformat(), "reason": reason},
        entity_type="daily_report",
        entity_id=report.public_id,
    )
    notifications.resolve(db, f"daily_report_overdue:{report.id}")
    notifications.resolve(db, f"daily_report_escalated:{report.id}")
    audit.record(
        db,
        action="daily_report.returned",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_user_id=actor_user_id,
        company_id=report.company_id,
        after={"reason": reason},
    )
    db.commit()
    return _many(db, [report])[0]


def request_change(db: Session, *, employee_id: int, device_id: int, public_id, data: dict, reason: str) -> dict:
    """After approval the driver asks for a change, with his reason; the reviewer decides (BR-06). Not once the
    month's payroll is approved: its figures are paid."""
    report = _drivers_report(db, employee_id, public_id)
    if report.status != "approved":
        raise AppError(409, "report_not_approved")
    if payroll.month_locked(db, report.company_id, report.business_date):
        raise AppError(409, "payroll_locked")
    driver = people.ref(db, employee_id)
    merged, before, after = _wanted(report, data, approved=True)
    if not after:
        raise AppError(422, "nothing_changed")
    _validate(db, driver, device_id, merged, new_shot="screenshot_sha256" in after)
    try:
        with db.begin_nested():
            change = _log(db, report, "request", "pending", before, after, reason=reason, created_by_device=device_id)
    except IntegrityError as exc:
        if violated_constraint(exc) == "report_changes_one_pending_idx":
            raise AppError(409, "change_request_exists") from None
        raise
    notifications.raise_alert(
        db,
        "daily_report_change_requested",
        company_id=report.company_id,
        entity_type="daily_report",
        entity_id=report.public_id,
        params={"driver": driver.name, "date": report.business_date.isoformat()},
        dedupe_key=f"daily_report_change:{change.id}",
    )
    audit.record(
        db,
        action="daily_report.change_requested",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_type="device",
        company_id=report.company_id,
        before=before,
        after=after | {"reason": reason},
    )
    db.commit()
    return _change_out(db, change, report)


def decide_change(
    db: Session, public_id, *, approve: bool, note: str | None, actor_user_id: int, all_companies: bool, company_ids
) -> dict:
    """The reviewer's decision on a change asked for after approval. Approved, the report takes the new figures and a
    cash difference is posted as an adjustment with the driver's reason; refused, the driver reads why."""
    row = db.execute(
        select(ReportChange, Report)
        .join(Report, Report.id == ReportChange.report_id)
        .where(ReportChange.public_id == public_id)
        .with_for_update()
    ).first()
    if row is None or not (all_companies or row[1].company_id in set(company_ids)):
        raise AppError(404, "change_not_found")
    change, report = row
    if change.status != "pending":
        raise AppError(409, "change_decided")
    if not approve and not note:
        raise AppError(422, "reason_required")
    driver = people.ref(db, report.employee_id)
    day = report.business_date.isoformat()
    if approve:
        if payroll.month_locked(db, report.company_id, report.business_date):
            raise AppError(409, "payroll_locked")
        for field, value in change.after.items():
            if field != "cash_amount":
                setattr(report, field, value)
        if "cash_amount" in change.after:
            new = Decimal(change.after["cash_amount"])
            old = report.approved_cash if report.approved_cash is not None else report.cash_amount
            cash.correct_approved(
                db,
                driver,
                report_id=report.id,
                difference=new - old,
                reason=change.reason,
                business_date=report.business_date,
                actor_user_id=actor_user_id,
            )
            report.cash_amount, report.approved_cash = new, new
        report.version += 1
        notifications.notify_driver(
            db,
            report.employee_id,
            "report_change_approved",
            params={"date": day},
            entity_type="daily_report",
            entity_id=report.public_id,
        )
    else:
        notifications.notify_driver(
            db,
            report.employee_id,
            "report_change_rejected",
            params={"date": day, "reason": note},
            entity_type="daily_report",
            entity_id=report.public_id,
        )
    change.status = "approved" if approve else "rejected"
    change.decided_by, change.decided_at, change.decision_note = actor_user_id, utcnow(), note
    notifications.resolve(db, f"daily_report_change:{change.id}")
    cash.check_balance_alert(db, driver)
    audit.record(
        db,
        action="daily_report.change_approved" if approve else "daily_report.change_rejected",
        entity_type="daily_report",
        entity_id=report.public_id,
        actor_user_id=actor_user_id,
        company_id=report.company_id,
        before=change.before,
        after=change.after | {"note": note},
    )
    db.commit()
    return _change_out(db, change, report)


def _change_out(db: Session, change: ReportChange, report: Report, names: dict | None = None) -> dict:
    names = names if names is not None else people.names(db, {report.employee_id})
    return {
        "id": str(change.public_id),
        "report_id": str(report.public_id),
        "driver": names.get(report.employee_id),
        "business_date": report.business_date,
        "kind": change.kind,
        "status": change.status,
        "before": change.before,
        "after": change.after,
        "reason": change.reason,
        "by_driver": change.created_by_device is not None,
        "created_at": change.created_at,
        "decided_at": change.decided_at,
        "decision_note": change.decision_note,
    }


def history(db: Session, public_id, **scope) -> list[dict]:
    """Every change to the report, oldest first."""
    report = _row(db, public_id, **scope)
    changes = db.scalars(select(ReportChange).where(ReportChange.report_id == report.id).order_by(ReportChange.id))
    names = people.names(db, {report.employee_id})
    return [_change_out(db, c, report, names) for c in changes]


def driver_history(db: Session, employee_id: int, public_id) -> list[dict]:
    report = db.scalar(select(Report).where(Report.public_id == public_id, Report.employee_id == employee_id))
    if report is None:
        raise AppError(404, "report_not_found")
    changes = db.scalars(select(ReportChange).where(ReportChange.report_id == report.id).order_by(ReportChange.id))
    return [_change_out(db, c, report, {}) for c in changes]


def pending_changes(db: Session, *, all_companies: bool, company_ids, limit: int = 100) -> list[dict]:
    """The changes drivers asked for after approval, waiting for a decision."""
    q = (
        select(ReportChange, Report)
        .join(Report, Report.id == ReportChange.report_id)
        .where(ReportChange.status == "pending")
        .order_by(ReportChange.created_at)
        .limit(min(limit, 500))
    )
    rows = list(db.execute(q if all_companies else q.where(Report.company_id.in_(list(company_ids)))))
    names = people.names(db, {r.employee_id for _, r in rows})
    return [_change_out(db, c, r, names) for c, r in rows]
