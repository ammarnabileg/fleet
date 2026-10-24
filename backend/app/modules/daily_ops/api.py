import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import sheets
from app.core.clock import KUWAIT, utcnow
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.daily_ops import schemas, service
from app.modules.files import service as files
from app.modules.i18n import service as i18n
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.org import printing
from app.modules.org import service as org
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["daily reports"])


@router.get(
    "/driver/reports/form", response_model=schemas.ReportFormOut, dependencies=[Depends(org.screen("daily_report"))]
)
def report_form(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """What the app asks in the daily report: this driver's platform's fields."""
    return service.form(db, people.ref(db, device.employee_id))


@router.post(
    "/driver/reports",
    response_model=schemas.ReportOut,
    status_code=201,
    dependencies=[Depends(org.screen("daily_report"))],
)
def submit(
    body: schemas.ReportIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.submit(db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump())


@router.get(
    "/driver/reports", response_model=list[schemas.ReportOut], dependencies=[Depends(org.screen("daily_report"))]
)
def my_reports(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.for_driver(db, device.employee_id)


@router.patch(
    "/driver/reports/{public_id}",
    response_model=schemas.ReportOut,
    dependencies=[Depends(org.screen("daily_report"))],
)
def edit_report(
    public_id: uuid.UUID,
    body: schemas.ReportEditIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.edit(
        db,
        employee_id=device.employee_id,
        device_id=device.device_id,
        public_id=public_id,
        data=body.model_dump(exclude_unset=True),
    )


@router.post(
    "/driver/reports/{public_id}/change-request",
    response_model=schemas.ChangeOut,
    status_code=201,
    dependencies=[Depends(org.screen("daily_report"))],
)
def request_change(
    public_id: uuid.UUID,
    body: schemas.ChangeRequestIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    data = body.model_dump(exclude_unset=True)
    reason = data.pop("reason")
    return service.request_change(
        db, employee_id=device.employee_id, device_id=device.device_id, public_id=public_id, data=data, reason=reason
    )


@router.get(
    "/driver/reports/{public_id}/changes",
    response_model=list[schemas.ChangeOut],
    dependencies=[Depends(org.screen("daily_report"))],
)
def my_report_changes(
    public_id: uuid.UUID, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.driver_history(db, device.employee_id, public_id)


@router.get("/daily-reports/change-requests", response_model=list[schemas.ChangeOut])
def change_requests(
    principal: Principal = Depends(require_permission("daily_reports.review")), db: Session = Depends(get_session)
):
    return service.pending_changes(db, **principal.scope)


@router.post("/daily-reports/change-requests/{public_id}/approve", response_model=schemas.ChangeOut)
def approve_change(
    public_id: uuid.UUID,
    body: schemas.DecisionIn,
    principal: Principal = Depends(require_permission("daily_reports.review")),
    db: Session = Depends(get_session),
):
    return service.decide_change(
        db, public_id, approve=True, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/daily-reports/change-requests/{public_id}/reject", response_model=schemas.ChangeOut)
def reject_change(
    public_id: uuid.UUID,
    body: schemas.DecisionIn,
    principal: Principal = Depends(require_permission("daily_reports.review")),
    db: Session = Depends(get_session),
):
    return service.decide_change(
        db, public_id, approve=False, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/daily-reports/{public_id}/changes", response_model=list[schemas.ChangeOut])
def report_changes(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("daily_reports.view")),
    db: Session = Depends(get_session),
):
    return service.history(db, public_id, **principal.scope)


@router.post("/daily-reports/{public_id}/send-back", response_model=schemas.ReportOut)
def send_back(
    public_id: uuid.UUID,
    body: schemas.RejectIn,
    principal: Principal = Depends(require_permission("daily_reports.review")),
    db: Session = Depends(get_session),
):
    return service.send_back(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.get("/daily-reports", response_model=list[schemas.ReportOut])
def list_reports(
    status: str | None = "submitted",
    business_date: date | None = None,
    driver_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("daily_reports.view")),
    db: Session = Depends(get_session),
):
    employee = people.ref_by_public_id(db, driver_id, **principal.scope).id if driver_id else None
    return service.list_reports(
        db,
        status=status,
        business_date=business_date,
        employee_id=employee,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_COLUMNS = (
    "driver",
    "vehicle",
    "business_date",
    "session",
    "orders",
    "valid_day",
    "cash",
    "approved_cash",
    "status",
    "late",
    "submitted_at",
    "reviewed_at",
    "review_note",
    "notes",
)
EXPORT_MAX = 20_000  # a year of a large fleet's reports for one status is far below this


@router.get("/daily-reports/export")
def export_reports(
    status: str | None = "submitted",
    business_date: date | None = None,
    driver_id: uuid.UUID | None = None,
    accept_language: str | None = Header(None),
    principal: Principal = Depends(require_permission("daily_reports.view")),
    db: Session = Depends(get_session),
):
    """The list as the panel filters it (status, day, driver), as Excel in the user's language with the shared print
    header (company, title, filters, who printed it and when), like the other reports."""
    if not principal.has("reports.export"):
        raise AppError(403, "permission_denied", permission="reports.export")
    employee = people.ref_by_public_id(db, driver_id, **principal.scope) if driver_id else None
    rows = service.list_reports(
        db,
        status=status,
        business_date=business_date,
        employee_id=employee.id if employee else None,
        limit=EXPORT_MAX,
        cap=EXPORT_MAX,
        **principal.scope,
    )
    lang = i18n.negotiate(db, principal.locale, accept_language)
    default = i18n.default_language(db).code

    def text(key: str, fallback: str, **params) -> str:
        value = i18n.t(db, lang, key, **params)
        return fallback if value == key else value

    def when(t) -> str:
        return t.astimezone(KUWAIT).strftime("%Y-%m-%d %H:%M") if t else ""

    def yes_no(value) -> str:
        return "" if value is None else text(f"daily_column.{'yes' if value else 'no'}", str(value))

    body = [
        [
            i18n.pick(r["driver"]["name"], lang, default) if r["driver"] else "",
            r["vehicle_plate"] or "",
            r["business_date"].isoformat(),
            r["session"],
            r["orders_count"],
            yes_no(r["valid_day"]),
            f"{r['cash_amount']:.3f}" if r["cash_amount"] is not None else "",
            f"{r['approved_cash']:.3f}" if r["approved_cash"] is not None else "",
            text(f"report_status.{r['status']}", r["status"]),
            yes_no(r["late"]),
            when(r["submitted_at"]),
            when(r["reviewed_at"]),
            r["review_note"] or "",
            r["notes"] or "",
        ]
        for r in rows
    ]
    title = text("daily_column.title", "daily reports")
    filters = [text(f"report_status.{status}", status) if status else text("daily_column.all", "all")]
    if business_date:
        filters.append(business_date.isoformat())
    if employee:
        filters.append(i18n.pick(employee.name, lang, default))
    layout = printing.layout(db, None, **principal.scope)
    heading = {
        "company": layout["identity"]["company"],
        "title": title,
        "filters": " · ".join(filters),
        "printed_at": utcnow().astimezone(KUWAIT).strftime("%Y-%m-%d %H:%M"),
        "printed_by": principal.full_name,
    }
    header = [text(f"daily_column.{c}", c) for c in EXPORT_COLUMNS]
    content = sheets.to_xlsx(title, header, body, rtl=lang == "ar", text_columns=(1, 2, 12, 13), heading=heading)
    name = "daily-reports" + (f"-{business_date.isoformat()}" if business_date else "") + f"-{status or 'all'}.xlsx"
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/daily-reports/{public_id}/screenshot")
def report_screenshot(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("daily_reports.view")),
    db: Session = Depends(get_session),
):
    info = service.screenshot(db, public_id, **principal.scope)
    return files.response(db, info)


@router.get("/daily-reports/{public_id}/evidence", response_model=schemas.EvidenceOut)
def report_evidence(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("daily_reports.view")),
    db: Session = Depends(get_session),
):
    return service.evidence(db, public_id, **principal.scope)


@router.get("/daily-reports/{public_id}/odometer/{which}")
def report_odometer_photo(
    public_id: uuid.UUID,
    which: Literal["start", "end"],
    principal: Principal = Depends(require_permission("daily_reports.view")),
    db: Session = Depends(get_session),
):
    info = service.odometer_photo(db, public_id, which, **principal.scope)
    return files.response(db, info)


@router.post("/daily-reports/{public_id}/approve", response_model=schemas.ReportOut)
def approve(
    public_id: uuid.UUID,
    body: schemas.ApproveIn,
    principal: Principal = Depends(require_permission("daily_reports.review")),
    db: Session = Depends(get_session),
):
    return service.approve(
        db,
        public_id,
        cash_amount=body.cash_amount,
        reason=body.reason,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/daily-reports/{public_id}/reject", response_model=schemas.ReportOut)
def reject(
    public_id: uuid.UUID,
    body: schemas.RejectIn,
    principal: Principal = Depends(require_permission("daily_reports.review")),
    db: Session = Depends(get_session),
):
    return service.reject(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)
