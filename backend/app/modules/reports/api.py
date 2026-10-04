from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.cash import service as cash
from app.modules.i18n import service as i18n
from app.modules.identity.service import Principal, require_permission
from app.modules.people import service as people
from app.modules.reports import schemas, service

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _csv(principal: Principal, filename: str, header: list[str], rows) -> Response:
    if not principal.has("reports.export"):
        raise AppError(403, "permission_denied", permission="reports.export")
    return Response(
        service.to_csv(header, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard", response_model=schemas.Dashboard, response_model_exclude_none=True)
def dashboard(principal: Principal = Depends(require_permission("dashboard.view")), db: Session = Depends(get_session)):
    return service.dashboard(db, permissions=principal.permissions, **principal.scope)


@router.get("/reports/daily-summary", response_model=schemas.SummaryOut)
def daily_summary(
    date_from: date,
    date_to: date,
    format: Literal["json", "csv"] = "json",
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    data = service.daily_summary(db, date_from=date_from, date_to=date_to, **principal.scope)
    if format == "json":
        return data
    lang = i18n.negotiate(db, principal.locale, accept_language)
    default = i18n.default_language(db).code
    header = ["employee_number", "driver", "days", "orders", "reported_cash", "approved_cash", "waiting", "rejected"]
    rows = [
        [
            r["employee_number"],
            service.name_in(r["driver"]["name"], lang, default),
            r["days"],
            r["orders"],
            f"{r['reported_cash']:.3f}",
            f"{r['approved_cash']:.3f}",
            r["waiting"],
            r["rejected"],
        ]
        for r in data["rows"]
    ]
    return _csv(principal, f"daily-summary-{date_from}-{date_to}.csv", header, rows)


@router.get("/reports/cash-balances")
def cash_balances(
    format: Literal["csv"] = "csv",
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("cash.view")),
    db: Session = Depends(get_session),
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
):
    lang = i18n.negotiate(db, principal.locale, accept_language)
    default = i18n.default_language(db).code
    drivers = people.app_drivers(db, **principal.scope) + people.departed_drivers(db, **principal.scope)
    rows = [
        [
            service.name_in(b["driver"]["name"], lang, default),
            f"{b['posted']:.3f}",
            f"{b['pending']:.3f}",
            f"{b['total']:.3f}",
            "yes" if b["over_limit"] else "",
        ]
        for b in cash.driver_balances(db, drivers)[:limit]
    ]
    return _csv(principal, "cash-balances.csv", ["driver", "approved", "unapproved", "total", "over_limit"], rows)


def _needs(principal: Principal, permission: str) -> None:
    if not principal.has(permission):
        raise AppError(403, "permission_denied", permission=permission)


def _money(value) -> str:
    return "" if value is None else f"{value:.3f}"


def _num(value) -> str:
    """A quantity or a percentage without trailing zeros: 3, 2.5, 33.33."""
    return "" if value is None else f"{value.normalize():f}"


def _hours(seconds) -> str:
    return "" if seconds is None else f"{seconds / 3600:.1f}"


@router.get("/reports/maintenance", response_model=schemas.MaintenanceReport)
def maintenance_report(
    date_from: date,
    date_to: date,
    format: Literal["json", "csv"] = "json",
    section: Literal["centers", "vehicles", "parts"] = "centers",
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """Time at the centers and the cost by center, by vehicle, and the parts (BRD FR-RPT-05)."""
    _needs(principal, "maintenance.view")
    data = service.maintenance_report(db, date_from=date_from, date_to=date_to, **principal.scope)
    if format == "json":
        return data
    name = f"maintenance-{section}-{date_from}-{date_to}.csv"
    if section == "centers":
        header = [
            "center",
            "received",
            "still_there",
            "avg_stay_hours",
            "max_stay_hours",
            "invoices",
            "cost",
            "avg_cost",
        ]
        rows = [
            [
                r["center"]["name"],
                r["received"],
                r["still_there"],
                _hours(r["avg_stay_seconds"]),
                _hours(r["max_stay_seconds"]),
                r["invoices"],
                _money(r["cost"]),
                _money(r["avg_cost"]),
            ]
            for r in data["by_center"]
        ]
    elif section == "vehicles":
        header = ["plate", "make", "model", "times_received", "stay_hours", "invoices", "cost"]
        rows = [
            [
                r["vehicle"]["plate_number"],
                r["vehicle"]["make"] or "",
                r["vehicle"]["model"] or "",
                r["times_received"],
                _hours(r["stay_seconds"]),
                r["invoices"],
                _money(r["cost"]),
            ]
            for r in data["by_vehicle"]
        ]
    else:
        header = ["part", "quantity", "amount", "invoices"]
        rows = [[r["description"], _num(r["quantity"]), _money(r["amount"]), r["invoices"]] for r in data["parts"]]
    return _csv(principal, name, header, rows)


@router.get("/reports/accidents", response_model=schemas.AccidentsReport)
def accidents_report(
    date_from: date,
    date_to: date,
    format: Literal["json", "csv"] = "json",
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """By driver, vehicle and outcome; estimate against the actual repair cost; deductions (BRD FR-RPT-06)."""
    _needs(principal, "accidents.view")
    data = service.accidents_report(db, date_from=date_from, date_to=date_to, **principal.scope)
    if format == "json":
        return data
    lang = i18n.negotiate(db, principal.locale, accept_language)
    default = i18n.default_language(db).code
    header = [
        "number",
        "occurred_at",
        "plate",
        "driver",
        "injuries",
        "police_report",
        "liability",
        "liability_percent",
        "estimate",
        "actual_cost",
        "difference",
        "deduction",
        "status",
    ]
    rows = [
        [
            r["number"],
            r["occurred_at"].astimezone(service.KUWAIT).strftime("%Y-%m-%d %H:%M"),
            r["vehicle"]["plate_number"] if r["vehicle"] else "",
            service.name_in(r["driver"]["name"], lang, default) if r["driver"] else "",
            "yes" if r["injuries"] else "",
            "yes" if r["has_police_report"] else "",
            r["liability"] or "",
            _num(r["liability_percent"]),
            _money(r["estimate"]),
            _money(r["actual_cost"]),
            _money(r["difference"]),
            _money(r["deduction"]),
            r["status"],
        ]
        for r in data["accidents"]
    ]
    return _csv(principal, f"accidents-{date_from}-{date_to}.csv", header, rows)
