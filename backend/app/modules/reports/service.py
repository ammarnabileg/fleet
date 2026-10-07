"""Dashboard and basic reports. This module may read every module's tables directly (architecture rule: reports
read all, write nothing), so each number is one SQL aggregate, always within the user's company scope.

Dashboard (BRD FR-DSH): every section appears only for a user holding its permission.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, today, utcnow
from app.core.errors import AppError
from app.modules.accidents import service as accidents
from app.modules.accidents.models import Accident
from app.modules.cash.models import Account, Journal, JournalLine, Receipt
from app.modules.daily_ops.models import Report
from app.modules.documents.models import Document
from app.modules.fines import service as fines
from app.modules.fleet.models import Custody, Vehicle
from app.modules.maintenance import service as maintenance
from app.modules.maintenance.models import Center, Invoice, InvoiceItem
from app.modules.maintenance.models import Request as MntRequest
from app.modules.notifications.models import Alert
from app.modules.org import service as org
from app.modules.payroll.models import Deduction
from app.modules.people.models import Employee
from app.modules.reports.filters import Filters
from app.modules.tracking.models import LastPosition

MAX_RANGE_DAYS = 93
ZERO = Decimal("0.000")


def _in_scope(column, all_companies: bool, company_ids: Iterable[int]):
    return literal(True) if all_companies else column.in_(list(company_ids))


def _vehicle_ok(column, filters: Filters):
    """A vehicle column within the vehicle and branch filters (FR-RPT-08)."""
    cond = literal(True)
    if filters.vehicle_id is not None:
        cond = and_(cond, column == filters.vehicle_id)
    if filters.branch_id is not None:
        cond = and_(cond, column.in_(select(Vehicle.id).where(Vehicle.branch_id == filters.branch_id)))
    return cond


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
        # the last seven days, today included, counted as today's figures are (reports not rejected, cash as reported)
        first = day - timedelta(days=6)
        by_day = {
            d: (n, int(o), Decimal(c))
            for d, n, o, c in db.execute(
                select(
                    Report.business_date,
                    func.count(),
                    func.coalesce(func.sum(Report.orders_count), 0),
                    func.coalesce(func.sum(Report.cash_amount), 0),
                )
                .where(scope, Report.business_date.between(first, day), Report.status != "rejected")
                .group_by(Report.business_date)
            )
        }
        out["week"] = [
            dict(zip(("day", "reports", "orders", "cash"), (d, *by_day.get(d, (0, 0, ZERO))), strict=True))
            for d in (first + timedelta(days=i) for i in range(7))
        ]
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

    if has("maintenance.view"):
        out["maintenance"] = maintenance.counts(db, all_companies=all_companies, company_ids=company_ids)

    if has("fines.view"):
        out["fines"] = fines.counts(db, all_companies=all_companies, company_ids=company_ids)

    if has("accidents.view"):
        out["accidents"] = accidents.counts(db, all_companies=all_companies, company_ids=company_ids)

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
    db: Session,
    *,
    date_from: date,
    date_to: date,
    filters: Filters = Filters(),
    all_companies: bool,
    company_ids: Iterable[int],
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
            Report.business_date.between(date_from, date_to),
            _in_scope(Report.company_id, all_companies, company_ids),
            Employee.id == filters.driver_id if filters.driver_id is not None else literal(True),
            Employee.branch_id == filters.branch_id if filters.branch_id is not None else literal(True),
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


def name_in(name: dict, lang: str, default: str) -> str:
    return name.get(lang) or name.get(default) or next(iter(name.values()), "")


# ------------------------------------------------------------------ maintenance and accidents (BRD FR-RPT-05, 06)

MAX_YEAR_DAYS = 366  # cost reports look at a year


def _period(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """The period as Kuwait days: from the first day's midnight to the midnight after the last day."""
    if date_to < date_from:
        raise AppError(422, "invalid_range")
    if (date_to - date_from).days >= MAX_YEAR_DAYS:
        raise AppError(422, "range_too_long_days", days=MAX_YEAR_DAYS)
    start = datetime.combine(date_from, time.min, tzinfo=KUWAIT)
    return start, datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=KUWAIT)


def _vehicle_cards(db: Session, ids) -> dict[int, dict]:
    ids = set(ids) - {None}
    if not ids:
        return {}
    return {
        v.id: {"id": str(v.public_id), "plate_number": v.plate_number, "make": v.make, "model": v.model}
        for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(ids)))
    }


def _people(db: Session, ids) -> dict[int, dict]:
    ids = set(ids) - {None}
    if not ids:
        return {}
    return {
        e.id: {"id": str(e.public_id), "name": e.name} for e in db.scalars(select(Employee).where(Employee.id.in_(ids)))
    }


def maintenance_report(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    filters: Filters = Filters(),
    all_companies: bool,
    company_ids: Iterable[int],
) -> dict:
    """Time at the centers (vehicles received in the period; a vehicle still there counts until now) and the cost
    (invoices approved and dated in the period): by center, by vehicle, and the parts replaced (FR-RPT-05)."""
    start, end = _period(date_from, date_to)
    now = utcnow()
    stay = func.extract("epoch", func.coalesce(MntRequest.picked_up_at, now) - MntRequest.received_at)
    received = and_(
        MntRequest.received_at >= start,
        MntRequest.received_at < end,
        _in_scope(MntRequest.company_id, all_companies, company_ids),
        _vehicle_ok(MntRequest.vehicle_id, filters),
    )
    approved = and_(
        Invoice.status == "approved",
        Invoice.invoice_date.between(date_from, date_to),
        _in_scope(Invoice.company_id, all_companies, company_ids),
        Invoice.request_id.in_(select(MntRequest.id).where(_vehicle_ok(MntRequest.vehicle_id, filters)))
        if filters.vehicle_id is not None or filters.branch_id is not None
        else literal(True),
    )
    stays = {
        r.center_id: r
        for r in db.execute(
            select(
                MntRequest.center_id,
                func.count().label("received"),
                func.count().filter(MntRequest.picked_up_at.is_(None)).label("still_there"),
                func.avg(stay).label("avg"),
                func.max(stay).label("max"),
            )
            .where(received)
            .group_by(MntRequest.center_id)
        )
    }
    costs = {
        r.center_id: r
        for r in db.execute(
            select(Invoice.center_id, func.count().label("n"), func.sum(Invoice.total).label("total"))
            .where(approved)
            .group_by(Invoice.center_id)
        )
    }
    centers = {c.id: c for c in db.scalars(select(Center).where(Center.id.in_(set(stays) | set(costs))))}
    by_center = []
    for cid in sorted(set(stays) | set(costs), key=lambda i: centers[i].name):
        s, c = stays.get(cid), costs.get(cid)
        total = Decimal(c.total) if c else ZERO
        by_center.append(
            {
                "center": {"id": str(centers[cid].public_id), "name": centers[cid].name},
                "received": s.received if s else 0,
                "still_there": s.still_there if s else 0,
                "avg_stay_seconds": int(s.avg) if s and s.avg is not None else None,
                "max_stay_seconds": int(s.max) if s and s.max is not None else None,
                "invoices": c.n if c else 0,
                "cost": total,
                "avg_cost": (total / c.n).quantize(Decimal("0.001")) if c else None,
            }
        )
    v_stays = {
        r.vehicle_id: r
        for r in db.execute(
            select(MntRequest.vehicle_id, func.count().label("n"), func.sum(stay).label("seconds"))
            .where(received)
            .group_by(MntRequest.vehicle_id)
        )
    }
    v_costs = {
        r.vehicle_id: r
        for r in db.execute(
            select(MntRequest.vehicle_id, func.count().label("n"), func.sum(Invoice.total).label("total"))
            .join(MntRequest, MntRequest.id == Invoice.request_id)
            .where(approved)
            .group_by(MntRequest.vehicle_id)
        )
    }
    cards = _vehicle_cards(db, set(v_stays) | set(v_costs))
    by_vehicle = sorted(
        (
            {
                "vehicle": cards[vid],
                "times_received": v_stays[vid].n if vid in v_stays else 0,
                "stay_seconds": int(v_stays[vid].seconds or 0) if vid in v_stays else 0,
                "invoices": v_costs[vid].n if vid in v_costs else 0,
                "cost": Decimal(v_costs[vid].total) if vid in v_costs else ZERO,
            }
            for vid in set(v_stays) | set(v_costs)
        ),
        key=lambda x: (-x["cost"], x["vehicle"]["plate_number"]),
    )
    amount = InvoiceItem.quantity * InvoiceItem.unit_price
    kinds = dict(
        db.execute(
            select(InvoiceItem.kind, func.sum(amount))
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(approved)
            .group_by(InvoiceItem.kind)
        ).all()
    )
    part = func.lower(func.trim(InvoiceItem.description))  # one line per part, however each center wrote it
    # its name as written, the same on every server (byte order: capitals first), not by the server's collation
    parts = [
        {
            "description": r.description,
            "quantity": Decimal(r.quantity),
            "amount": Decimal(r.amount).quantize(Decimal("0.001")),
            "invoices": r.invoices,
        }
        for r in db.execute(
            select(
                func.min(func.trim(InvoiceItem.description).collate("C")).label("description"),
                func.sum(InvoiceItem.quantity).label("quantity"),
                func.sum(amount).label("amount"),
                func.count(func.distinct(InvoiceItem.invoice_id)).label("invoices"),
            )
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(approved, InvoiceItem.kind == "part")
            .group_by(part)
            .order_by(func.sum(amount).desc(), part)
            .limit(100)
        )
    ]
    all_stays = [x for x in by_center if x["avg_stay_seconds"] is not None]
    received_n = sum(x["received"] for x in by_center)
    return {
        "from": date_from,
        "to": date_to,
        "totals": {
            "received": received_n,
            "still_there": sum(x["still_there"] for x in by_center),
            "avg_stay_seconds": (
                int(sum(x["avg_stay_seconds"] * x["received"] for x in all_stays) / received_n) if received_n else None
            ),
            "invoices": sum(x["invoices"] for x in by_center),
            "cost": sum((x["cost"] for x in by_center), ZERO),
            "parts": Decimal(kinds.get("part") or 0).quantize(Decimal("0.001")),
            "labour": Decimal(kinds.get("labour") or 0).quantize(Decimal("0.001")),
            "other": Decimal(kinds.get("other") or 0).quantize(Decimal("0.001")),
        },
        "by_center": by_center,
        "by_vehicle": by_vehicle,
        "parts": parts,
    }


def accidents_report(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    filters: Filters = Filters(),
    all_companies: bool,
    company_ids: Iterable[int],
) -> dict:
    """Accidents that happened in the period (not the cancelled ones): by driver, by vehicle and by outcome, the
    approved estimate against the actual repair cost, and the deductions; plus every open accident still waiting
    for its police report, whatever its date (FR-RPT-06)."""
    start, end = _period(date_from, date_to)
    scope = and_(
        _in_scope(Accident.company_id, all_companies, company_ids),
        _vehicle_ok(Accident.vehicle_id, filters),
        Accident.driver_id == filters.driver_id if filters.driver_id is not None else literal(True),
    )
    rows = list(
        db.scalars(
            select(Accident)
            .where(Accident.occurred_at >= start, Accident.occurred_at < end, Accident.status != "cancelled", scope)
            .order_by(Accident.occurred_at, Accident.id)
        )
    )
    repair_ids = [a.repair_request_id for a in rows if a.repair_request_id]
    actual = (
        dict(
            db.execute(
                select(Invoice.request_id, func.sum(Invoice.total))
                .where(Invoice.request_id.in_(repair_ids), Invoice.status == "approved")
                .group_by(Invoice.request_id)
            ).all()
        )
        if repair_ids
        else {}
    )
    deducted = (
        dict(
            db.execute(
                select(Deduction.source_id, Deduction.total).where(
                    Deduction.source_type == "accident",
                    Deduction.status == "approved",
                    Deduction.source_id.in_([a.id for a in rows]),
                )
            ).all()
        )
        if rows
        else {}
    )
    waiting = list(
        db.scalars(
            select(Accident)
            .where(Accident.status == "open", Accident.police_report_sha256.is_(None), scope)
            .order_by(Accident.created_at)
        )
    )
    cards = _vehicle_cards(db, {a.vehicle_id for a in rows + waiting})
    names = _people(db, {a.driver_id for a in rows + waiting})
    estimate = {a.id: a.estimate_total if a.estimate_status == "approved" else None for a in rows}

    def line(a: Accident) -> dict:
        cost = actual.get(a.repair_request_id)
        return {
            "id": str(a.public_id),
            "number": a.number,
            "occurred_at": a.occurred_at,
            "vehicle": cards.get(a.vehicle_id),
            "driver": names.get(a.driver_id),
            "injuries": a.injuries,
            "liability": a.liability,
            "liability_percent": a.liability_percent,
            "has_police_report": a.police_report_sha256 is not None,
            "estimate": estimate[a.id],
            "actual_cost": Decimal(cost) if cost is not None else None,
            "difference": (Decimal(cost) - estimate[a.id]) if cost is not None and estimate[a.id] else None,
            "deduction": deducted.get(a.id),
            "status": a.status,
        }

    lines = [line(a) for a in rows]

    def group(key) -> list[dict]:
        out: dict = {}
        for x in lines:
            ref = x[key]
            k = ref["id"] if ref else None
            g = out.setdefault(
                k,
                {key: ref, "accidents": 0, "liable": 0, "estimate": ZERO, "actual_cost": ZERO, "deduction": ZERO},
            )
            g["accidents"] += 1
            g["liable"] += x["liability"] in ("driver", "shared")
            g["estimate"] += x["estimate"] or ZERO
            g["actual_cost"] += x["actual_cost"] or ZERO
            g["deduction"] += x["deduction"] or ZERO
        return sorted(out.values(), key=lambda g: (-g["accidents"], -g["estimate"]))

    now = utcnow()
    return {
        "from": date_from,
        "to": date_to,
        "totals": {
            "accidents": len(lines),
            "injuries": sum(1 for x in lines if x["injuries"]),
            "estimate": sum((x["estimate"] or ZERO for x in lines), ZERO),
            "actual_cost": sum((x["actual_cost"] or ZERO for x in lines), ZERO),
            "deduction": sum((x["deduction"] or ZERO for x in lines), ZERO),
            "waiting_police_report": len(waiting),
        },
        "by_outcome": {
            k: sum(1 for x in lines if (x["liability"] or "pending") == k)
            for k in ("pending", "none", "driver", "shared")
        },
        "by_driver": group("driver"),
        "by_vehicle": group("vehicle"),
        "accidents": lines,
        "waiting_police_report": [
            {
                "id": str(a.public_id),
                "number": a.number,
                "occurred_at": a.occurred_at,
                "vehicle": cards.get(a.vehicle_id),
                "driver": names.get(a.driver_id),
                "days": (now - a.created_at).days,
            }
            for a in waiting
        ],
    }
