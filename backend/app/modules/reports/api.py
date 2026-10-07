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
from app.modules.reports import cash_report, export, filters, kilometers, payroll_report, schemas, service

router = APIRouter(prefix="/api/v1", tags=["reports"])

Format = Literal["json", "csv", "xlsx"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Out:
    """How a report leaves: CSV with the column keys for other systems, Excel in the user's language for people."""

    def __init__(self, db: Session, principal: Principal, accept_language: str | None):
        self.db, self.principal = db, principal
        self.lang = i18n.negotiate(db, principal.locale, accept_language)
        self.default = i18n.default_language(db).code

    def name(self, name: dict) -> str:
        return service.name_in(name, self.lang, self.default)

    def send(self, fmt: str, base: str, title: str, header: list[str], rows) -> Response:
        if not self.principal.has("reports.export"):
            raise AppError(403, "permission_denied", permission="reports.export")
        if fmt == "csv":
            body, media, ext = export.to_csv(header, rows), "text/csv; charset=utf-8", "csv"
        else:
            labels = [i18n.t(self.db, self.lang, f"report_column.{h}") for h in header]
            labels = [lab if not lab.startswith("report_column.") else h for lab, h in zip(labels, header, strict=True)]
            sheet = i18n.t(self.db, self.lang, f"report_title.{title}")
            body = export.to_xlsx(sheet, labels, rows, rtl=self.lang == "ar")
            media, ext = XLSX, "xlsx"
        return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{base}.{ext}"'})


def _scope(db: Session, principal: Principal, p: filters.FilterParams) -> tuple[dict, filters.Filters]:
    return filters.resolve(db, p, **principal.scope)


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


def _tenths(value) -> str:
    return "" if value is None else f"{value:.1f}"


def _plate(v: dict | None) -> str:
    return v["plate_number"] if v else ""


@router.get("/dashboard", response_model=schemas.Dashboard, response_model_exclude_none=True)
def dashboard(principal: Principal = Depends(require_permission("dashboard.view")), db: Session = Depends(get_session)):
    return service.dashboard(db, permissions=principal.permissions, user_id=principal.user_id, **principal.scope)


@router.get("/reports/daily-summary", response_model=schemas.SummaryOut)
def daily_summary(
    date_from: date,
    date_to: date,
    format: Format = "json",
    section: Literal["drivers", "days", "companies"] = "drivers",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    scope, f = _scope(db, principal, p)
    data = service.daily_summary(db, date_from=date_from, date_to=date_to, filters=f, **scope)
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
    if section == "drivers":
        header = [
            "employee_number",
            "driver",
            "days",
            "orders",
            "reported_cash",
            "approved_cash",
            "waiting",
            "rejected",
            "late",
        ]
        rows = [
            [
                r["employee_number"],
                out.name(r["driver"]["name"]),
                r["days"],
                r["orders"],
                f"{r['reported_cash']:.3f}",
                f"{r['approved_cash']:.3f}",
                r["waiting"],
                r["rejected"],
                r["late"],
            ]
            for r in data["rows"]
        ]
    else:
        first = "day" if section == "days" else "company"
        header = [first, "sent", "late", "rejected", "orders", "reported_cash", "approved_cash"]
        source = data["by_day"] if section == "days" else data["by_company"]
        rows = [
            [
                str(r["day"]) if section == "days" else out.name(r["name"] or {}),
                r["sent"],
                r["late"],
                r["rejected"],
                r["orders"],
                _money(r["reported_cash"]),
                _money(r["approved_cash"]),
            ]
            for r in source
        ]
    return out.send(format, f"daily-{section}-{date_from}-{date_to}", "daily", header, rows)


@router.get("/reports/fleet", response_model=schemas.FleetReport)
def fleet_report(
    date_from: date,
    date_to: date,
    format: Format = "json",
    section: Literal["vehicles", "days"] = "vehicles",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """The vehicles by status, those with no driver, and their daily use over the period (FR-RPT-01)."""
    _needs(principal, "vehicles.view")
    scope, f = _scope(db, principal, p)
    data = service.fleet_report(db, date_from=date_from, date_to=date_to, filters=f, **scope)
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
    if section == "vehicles":
        header = ["plate", "make", "model", "status", "driver", "days_held", "use_percent"]
        rows = [
            [
                _plate(r["vehicle"]),
                r["vehicle"]["make"] or "",
                r["vehicle"]["model"] or "",
                i18n.t(db, out.lang, f"vehicle_status.{r['status']}"),
                out.name(r["driver"]["name"]) if r["driver"] else "",
                r["days_held"],
                _tenths(r["use_percent"]),
            ]
            for r in data["by_vehicle"]
        ]
    else:
        header = ["day", "in_use", "vehicles"]
        rows = [[str(r["day"]), r["in_use"], r["vehicles"]] for r in data["by_day"]]
    return out.send(format, f"fleet-{section}-{date_from}-{date_to}", "fleet", header, rows)


@router.get("/reports/cash-balances")
def cash_balances(
    format: Literal["csv", "xlsx"] = "csv",
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("cash.view")),
    db: Session = Depends(get_session),
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
):
    out = Out(db, principal, accept_language)
    drivers = people.app_drivers(db, **principal.scope) + people.departed_drivers(db, **principal.scope)
    rows = [
        [
            out.name(b["driver"]["name"]),
            f"{b['posted']:.3f}",
            f"{b['pending']:.3f}",
            f"{b['total']:.3f}",
            "yes" if b["over_limit"] else "",
        ]
        for b in cash.driver_balances(db, drivers)[:limit]
    ]
    header = ["driver", "approved", "unapproved", "total", "over_limit"]
    return out.send(format, "cash-balances", "cash_balances", header, rows)


@router.get("/reports/maintenance", response_model=schemas.MaintenanceReport)
def maintenance_report(
    date_from: date,
    date_to: date,
    format: Format = "json",
    section: Literal["centers", "vehicles", "parts"] = "centers",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """Time at the centers and the cost by center, by vehicle, and the parts (BRD FR-RPT-05)."""
    _needs(principal, "maintenance.view")
    scope, f = _scope(db, principal, p)
    data = service.maintenance_report(db, date_from=date_from, date_to=date_to, filters=f, **scope)
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
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
    return out.send(format, f"maintenance-{section}-{date_from}-{date_to}", "maintenance", header, rows)


@router.get("/reports/accidents", response_model=schemas.AccidentsReport)
def accidents_report(
    date_from: date,
    date_to: date,
    format: Format = "json",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """By driver, vehicle and outcome; estimate against the actual repair cost; deductions (BRD FR-RPT-06)."""
    _needs(principal, "accidents.view")
    scope, f = _scope(db, principal, p)
    data = service.accidents_report(db, date_from=date_from, date_to=date_to, filters=f, **scope)
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
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
            _plate(r["vehicle"]),
            out.name(r["driver"]["name"]) if r["driver"] else "",
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
    return out.send(format, f"accidents-{date_from}-{date_to}", "accidents", header, rows)


@router.get("/reports/kilometers", response_model=schemas.KilometersReport)
def kilometers_report(
    date_from: date,
    date_to: date,
    format: Format = "json",
    section: Literal["vehicles", "drivers", "pending"] = "vehicles",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """By vehicle and driver, off duty, the readings waiting for review, the odometer against the GPS (FR-RPT-03)."""
    _needs(principal, "odometer.view")
    scope, f = _scope(db, principal, p)
    data = kilometers.kilometers_report(db, date_from=date_from, date_to=date_to, filters=f, **scope)
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
    if section == "vehicles":
        header = [
            "plate",
            "make",
            "model",
            "km",
            "on_duty",
            "off_duty",
            "unattended",
            "center",
            "with_driver",
            "gps",
            "difference",
            "difference_percent",
        ]
        rows = [
            [
                _plate(r["vehicle"]),
                (r["vehicle"] or {}).get("make") or "",
                (r["vehicle"] or {}).get("model") or "",
                r["km"],
                r["on_duty"],
                r["off_duty"],
                r["unattended"],
                r["center"],
                r["with_driver"],
                _tenths(r["gps"]),
                _tenths(r["difference"]),
                _tenths(r["difference_percent"]),
            ]
            for r in data["by_vehicle"]
        ]
    elif section == "drivers":
        header = ["driver", "days", "on_duty", "off_duty", "gps", "km_per_day"]
        rows = [
            [
                out.name(r["driver"]["name"]) if r["driver"] else "",
                r["days"],
                r["on_duty"],
                r["off_duty"],
                _tenths(r["gps"]),
                _tenths(r["km_per_day"]),
            ]
            for r in data["by_driver"]
        ]
    else:
        header = ["recorded_at", "plate", "driver", "kind", "value_km", "flags"]
        rows = [
            [
                r["recorded_at"].astimezone(service.KUWAIT).strftime("%Y-%m-%d %H:%M"),
                _plate(r["vehicle"]),
                out.name(r["driver"]["name"]) if r["driver"] else "",
                r["kind"],
                r["value_km"],
                " ".join(r["flags"]),
            ]
            for r in data["pending"]
        ]
    return out.send(format, f"kilometers-{section}-{date_from}-{date_to}", "kilometers", header, rows)


@router.get("/reports/cash", response_model=schemas.CashReport)
def cash_report_(
    date_from: date,
    date_to: date,
    format: Format = "json",
    section: Literal["aging", "collectors", "treasury", "deposits"] = "aging",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """The drivers' balances and their age, the receipts by collector, the treasury and the deposits (FR-RPT-04)."""
    _needs(principal, "cash.view")
    if format != "json" and section in ("treasury", "deposits"):
        _needs(principal, "treasury.view")
    scope, f = _scope(db, principal, p)
    data = cash_report.cash_report(
        db,
        date_from=date_from,
        date_to=date_to,
        filters=f,
        with_treasury=principal.has("treasury.view"),
        **scope,
    )
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
    if section == "aging":
        header = ["driver", "approved", "unapproved", "d0_1", "d2_3", "d4_7", "d8_plus", "oldest"]
        rows = [
            [
                out.name(r["driver"]["name"]) if r["driver"] else "",
                _money(r["posted"]),
                _money(r["pending"]),
                _money(r["d0_1"]),
                _money(r["d2_3"]),
                _money(r["d4_7"]),
                _money(r["d8_plus"]),
                str(r["oldest"] or ""),
            ]
            for r in data["aging"]["rows"]
        ]
    elif section == "collectors":
        header = ["user", "receipts", "amount", "confirmed", "reversed"]
        rows = [
            [r["user"], r["receipts"], _money(r["amount"]), r["confirmed"], r["reversed"]] for r in data["collectors"]
        ]
    elif section == "treasury":
        header = ["branch", "opening", "received", "paid_out", "closing"]
        rows = [
            [
                out.name(r["branch"]["name"]) if r["branch"] else "",
                *(_money(r[k]) for k in ("opening", "received", "paid_out", "closing")),
            ]
            for r in data["treasury"]
        ]
    else:
        header = ["business_date", "branch", "amount", "reference", "by", "reversed"]
        rows = [
            [
                str(r["business_date"]),
                out.name(r["branch"]["name"]) if r["branch"] else "",
                _money(r["amount"]),
                r["reference"] or "",
                r["by"],
                "yes" if r["reversed"] else "",
            ]
            for r in data["deposits"]
        ]
    return out.send(format, f"cash-{section}-{date_from}-{date_to}", "cash", header, rows)


@router.get("/reports/payroll", response_model=schemas.PayrollReport)
def payroll_report_(
    month_from: date,
    month_to: date,
    format: Format = "json",
    section: Literal["runs", "carried"] = "runs",
    p: filters.FilterParams = Depends(filters.params),
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("reports.view")),
    db: Session = Depends(get_session),
):
    """By month and company, the installments by source and what was carried forward (FR-RPT-07)."""
    _needs(principal, "payroll.view")
    scope, f = _scope(db, principal, p)
    data = payroll_report.payroll_report(db, month_from=month_from, month_to=month_to, filters=f, **scope)
    if format == "json":
        return data
    out = Out(db, principal, accept_language)
    if section == "runs":
        header = [
            "month",
            "company",
            "status",
            "lines",
            "gross",
            "deductions",
            "net",
            "installments_due",
            "installments_deducted",
            "carried",
        ]
        money = ("gross", "deductions", "net", "installments_due", "installments_deducted", "carried")
        rows = [
            [r["month"].strftime("%Y-%m"), out.name(r["company"]["name"] or {}), r["status"], r["lines"]]
            + [_money(r[k]) for k in money]
            for r in data["runs"]
        ]
    else:
        header = ["month", "employee", "source_type", "reason", "due", "deducted", "carried"]
        rows = [
            [
                r["month"].strftime("%Y-%m"),
                out.name(r["employee"]["name"]) if r["employee"] else "",
                r["source_type"],
                r["reason"],
                _money(r["due"]),
                _money(r["deducted"]),
                _money(r["carried"]),
            ]
            for r in data["carried"]
        ]
    return out.send(format, f"payroll-{section}-{month_from:%Y-%m}-{month_to:%Y-%m}", "payroll", header, rows)
