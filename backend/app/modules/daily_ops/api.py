import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.daily_ops import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
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
