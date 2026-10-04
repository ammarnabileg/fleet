import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.daily_ops import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["daily reports"])


@router.post("/driver/reports", response_model=schemas.ReportOut, status_code=201)
def submit(
    body: schemas.ReportIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.submit(db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump())


@router.get("/driver/reports", response_model=list[schemas.ReportOut])
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
    return FileResponse(
        files.path_of(info.sha256),
        media_type=info.content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


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
