"""Dashboard and basic reports. This module may read every module's tables directly (architecture rule: reports
read all, write nothing), so each number is one SQL aggregate, always within the user's company scope.

Dashboard (BRD FR-DSH): every section appears only for a user holding its permission.
"""

import csv
import io
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.modules.cash.models import Account, Journal, JournalLine, Receipt
from app.modules.daily_ops.models import Report
from app.modules.documents.models import Document
from app.modules.fleet.models import Custody, Vehicle
from app.modules.notifications.models import Alert
from app.modules.org import service as org
from app.modules.people.models import Employee
from app.modules.tracking.models import LastPosition

MAX_RANGE_DAYS = 93
ZERO = Decimal("0.000")


def _in_scope(column, all_companies: bool, company_ids: Iterable[int]):
    return literal(True) if all_companies else column.in_(list(company_ids))


# ------------------------------------------------------------------ dashboard


def dashboard(db: Session, *, permissions: frozenset[str], all_companies: bool, company_ids: Iterable[int]) -> dict:
    company_ids = list(company_ids)
    out: dict = {"as_of": utcnow()}
    has = permissions.__contains__

    if has("vehicles.view"):
        rows = db.execute(
            select(Vehicle.status, func.count())
            .where(_in_scope(Vehicle.company_id, all_companies, company_ids))
            .group_by(Vehicle.status)
        ).all()
        out["vehicles"] = {"available": 0, "assigned": 0, "maintenance": 0, "accident": 0, "inactive": 0} | dict(rows)

    if has("custody.view") or has("tracking.live"):
        lost_after = timedelta(minutes=org.get_section(db, "tracking").signal_loss_minutes)
        reference = func.coalesce(
            case((LastPosition.custody_id == Custody.id, LastPosition.recorded_at)), Custody.started_at
        )
        on_duty, lost = db.execute(
            select(func.count(), func.count().filter(reference < utcnow() - lost_after))
            .select_from(Custody)
            .outerjoin(LastPosition, LastPosition.vehicle_id == Custody.vehicle_id)
            .where(Custody.ended_at.is_(None), _in_scope(Custody.company_id, all_companies, company_ids))
        ).one()
        out["drivers"] = {"on_duty": on_duty, "signal_lost": lost if has("tracking.live") else None}

    if has("daily_reports.view"):
        day = today()
        scope = _in_scope(Report.company_id, all_companies, company_ids)
        sent, orders, cash_ = db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Report.orders_count), 0),
                func.coalesce(func.sum(Report.cash_amount), 0),
            ).where(scope, Report.business_date == day, Report.status != "rejected")
        ).one()
        hours = org.get_section(db, "cash").report_review_hours
        waiting, overdue = db.execute(
            select(func.count(), func.count().filter(Report.submitted_at < utcnow() - timedelta(hours=hours))).where(
                scope, Report.status == "submitted"
            )
        ).one()
        drivers_on_duty = out.get("drivers", {}).get("on_duty")
        out["daily_reports"] = {
            "today_sent": sent,
            "today_orders": int(orders),
            "today_cash": Decimal(cash_),
            "waiting_review": waiting,
            "overdue": overdue,
            "drivers_on_duty": drivers_on_duty,
        }

    if has("cash.view"):
        driver_scope = _in_scope(Employee.company_id, all_companies, company_ids)
        per_driver = (
            select(
                Account.driver_id,
                func.coalesce(func.sum(JournalLine.amount).filter(Journal.status == "posted"), 0).label("posted"),
                func.coalesce(func.sum(JournalLine.amount).filter(Journal.status == "pending"), 0).label("pending"),
            )
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(Journal, Journal.id == JournalLine.journal_id)
            .join(Employee, Employee.id == Account.driver_id)
            .where(Account.kind == "driver", driver_scope)
            .group_by(Account.driver_id)
            .subquery()
        )
        limit = org.get_section(db, "cash").driver_balance_alert
        posted, pending, over = db.execute(
            select(
                func.coalesce(func.sum(per_driver.c.posted), 0),
                func.coalesce(func.sum(per_driver.c.pending), 0),
                func.count().filter(per_driver.c.posted + per_driver.c.pending > limit),
            )
        ).one()
        deposited = db.scalar(
            select(func.coalesce(func.sum(Receipt.amount), 0))
            .join(Employee, Employee.id == Receipt.driver_id)
            .where(driver_scope, func.date(func.timezone("Asia/Kuwait", Receipt.created_at)) == today())
        )
        out["cash"] = {
            "held_by_drivers": Decimal(posted) + Decimal(pending),
            "unapproved": Decimal(pending),
            "approved": Decimal(posted),
            "over_limit": over,
            "deposited_today": Decimal(deposited),
            "limit": limit,
        }

    if has("documents.view"):
        horizon = today() + timedelta(days=org.get_section(db, "documents").expiry_alert_days)
        expiring, expired = db.execute(
            select(
                func.count().filter(Document.expiry_date >= today()),
                func.count().filter(Document.expiry_date < today()),
            ).where(
                Document.is_current.is_(True),
                Document.expiry_date <= horizon,
                _in_scope(Document.company_id, all_companies, company_ids),
            )
        ).one()
        out["documents"] = {"expiring": expiring, "expired": expired}

    visible = Alert.permission.in_(list(permissions))
    alert_scope = literal(True) if all_companies else or_(Alert.company_id.is_(None), Alert.company_id.in_(company_ids))
    rows = db.execute(
        select(Alert.severity, func.count())
        .where(visible, alert_scope, Alert.acknowledged_at.is_(None))
        .group_by(Alert.severity)
    ).all()
    out["alerts"] = {"critical": 0, "warning": 0, "info": 0} | dict(rows)
    return out


# ------------------------------------------------------------------ reports


def _range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise AppError(422, "invalid_range")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise AppError(422, "range_too_long", hours=MAX_RANGE_DAYS * 24)


def daily_summary(
    db: Session, *, date_from: date, date_to: date, all_companies: bool, company_ids: Iterable[int]
) -> dict:
    """Per driver over a period: days reported, orders, cash reported and approved, reports waiting or rejected."""
    _range(date_from, date_to)
    live = Report.status != "rejected"
    rows = db.execute(
        select(
            Employee.public_id,
            Employee.employee_number,
            Employee.name,
            Employee.company_id,
            func.count().filter(live).label("days"),
            func.coalesce(func.sum(Report.orders_count).filter(live), 0).label("orders"),
            func.coalesce(func.sum(Report.cash_amount).filter(live), 0).label("reported_cash"),
            func.coalesce(func.sum(Report.approved_cash).filter(Report.status == "approved"), 0).label("approved_cash"),
            func.count().filter(Report.status == "submitted").label("waiting"),
            func.count().filter(Report.status == "rejected").label("rejected"),
        )
        .join(Employee, Employee.id == Report.employee_id)
        .where(
            Report.business_date.between(date_from, date_to), _in_scope(Report.company_id, all_companies, company_ids)
        )
        .group_by(Employee.id)
        .order_by(Employee.employee_number)
    ).all()
    out = [
        {
            "driver": {"id": str(r.public_id), "name": r.name},
            "employee_number": r.employee_number,
            "company_id": r.company_id,
            "days": r.days,
            "orders": int(r.orders),
            "reported_cash": Decimal(r.reported_cash),
            "approved_cash": Decimal(r.approved_cash),
            "waiting": r.waiting,
            "rejected": r.rejected,
        }
        for r in rows
    ]
    totals = {
        k: sum((x[k] for x in out), Decimal(0) if "cash" in k else 0)
        for k in ("days", "orders", "reported_cash", "approved_cash", "waiting", "rejected")
    }
    return {"from": date_from, "to": date_to, "rows": out, "totals": totals}


def _safe(value) -> str:
    """CSV cells that a spreadsheet would run as a formula are prefixed (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(header: list[str], rows: Iterable[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows([[_safe(v) for v in row] for row in rows])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # the BOM makes Excel read Arabic correctly


def name_in(name: dict, lang: str, default: str) -> str:
    return name.get(lang) or name.get(default) or next(iter(name.values()), "")
