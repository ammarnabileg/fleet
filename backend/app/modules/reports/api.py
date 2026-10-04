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
