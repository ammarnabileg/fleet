import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.accidents import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission

router = APIRouter(prefix="/api/v1", tags=["accidents"])

Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


def _file(info: files.FileInfo) -> FileResponse:
    return FileResponse(
        files.path_of(info.sha256),
        media_type=info.content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


# ------------------------------------------------------------------ the office


@router.get("/accidents", response_model=list[schemas.AccidentOut])
def list_accidents(
    stage: str | None = None,
    status: str | None = None,
    no_police_report: bool = False,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
    principal: Principal = Depends(require_permission("accidents.view")),
    db: Session = Depends(get_session),
):
    return service.list_accidents(
        db,
        stage_filter=stage,
        status=status,
        no_police_report=no_police_report,
        vehicle_public_id=vehicle_id,
        driver_public_id=driver_id,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/accidents", response_model=schemas.AccidentDetailOut, status_code=201)
def create(
    body: schemas.AccidentIn,
    principal: Principal = Depends(require_permission("accidents.create")),
    db: Session = Depends(get_session),
):
    return service.create(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.get("/accidents/{public_id}", response_model=schemas.AccidentDetailOut)
def get(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("accidents.view")),
    db: Session = Depends(get_session),
):
    return service.get(db, public_id, **principal.scope)


@router.post("/accidents/{public_id}/photos", response_model=schemas.AccidentDetailOut)
def add_photos(
    public_id: uuid.UUID,
    body: schemas.PhotosIn,
    principal: Principal = Depends(require_permission("accidents.create")),
    db: Session = Depends(get_session),
):
    return service.add_photos(db, public_id, photos=body.photos, actor_user_id=principal.user_id, **principal.scope)


@router.post("/accidents/{public_id}/police-report", response_model=schemas.AccidentDetailOut)
def police_report(
    public_id: uuid.UUID,
    body: schemas.PoliceReportIn,
    principal: Principal = Depends(require_permission("accidents.create")),
    db: Session = Depends(get_session),
):
    return service.police_report(
        db, public_id, data=body.model_dump(), actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/accidents/{public_id}/refer", response_model=schemas.AccidentDetailOut)
def refer(
    public_id: uuid.UUID,
    body: schemas.ReferIn,
    principal: Principal = Depends(require_permission("accidents.update")),
    db: Session = Depends(get_session),
):
    return service.refer(
        db,
        public_id,
        center_public_id=body.center_id,
        note=body.note,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/accidents/{public_id}/estimate/approve", response_model=schemas.AccidentDetailOut)
def approve_estimate(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("accidents.update")),
    db: Session = Depends(get_session),
):
    return service.decide_estimate(
        db, public_id, approve=True, reason=None, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/accidents/{public_id}/estimate/reject", response_model=schemas.AccidentDetailOut)
def reject_estimate(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("accidents.update")),
    db: Session = Depends(get_session),
):
    return service.decide_estimate(
        db, public_id, approve=False, reason=body.reason, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/accidents/{public_id}/outcome", response_model=schemas.AccidentDetailOut)
def outcome(
    public_id: uuid.UUID,
    body: schemas.OutcomeIn,
    principal: Principal = Depends(require_permission("accidents.approve")),
    db: Session = Depends(get_session),
):
    return service.record_outcome(
        db, public_id, data=body.model_dump(), actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/accidents/{public_id}/repair", response_model=schemas.AccidentDetailOut)
def repair(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("accidents.update")),
    db: Session = Depends(get_session),
):
    return service.create_repair(db, public_id, actor_user_id=principal.user_id, **principal.scope)


@router.post("/accidents/{public_id}/close", response_model=schemas.AccidentDetailOut)
def close(
    public_id: uuid.UUID,
    body: schemas.NoteIn,
    principal: Principal = Depends(require_permission("accidents.approve")),
    db: Session = Depends(get_session),
):
    return service.close(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


@router.post("/accidents/{public_id}/cancel", response_model=schemas.AccidentDetailOut)
def cancel(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("accidents.update")),
    db: Session = Depends(get_session),
):
    return service.cancel(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.get("/accidents/{public_id}/files/{sha256}")
def accident_file(
    public_id: uuid.UUID,
    sha256: str,
    principal: Principal = Depends(require_permission("accidents.view")),
    db: Session = Depends(get_session),
):
    return _file(service.accident_file(db, public_id, sha256, **principal.scope))


# ------------------------------------------------------------------ the center's portal


@router.get("/portal/accidents", response_model=list[schemas.PortalAccidentOut])
def portal_list(
    active: bool = True,
    principal: Principal = Depends(require_permission("portal.damage")),
    db: Session = Depends(get_session),
):
    return service.portal_list(db, user_id=principal.user_id, active=active)


@router.get("/portal/accidents/{public_id}", response_model=schemas.PortalAccidentOut)
def portal_get(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("portal.damage")),
    db: Session = Depends(get_session),
):
    return service.portal_get(db, public_id, user_id=principal.user_id)


@router.post("/portal/accidents/{public_id}/estimate", response_model=schemas.PortalAccidentOut)
def submit_estimate(
    public_id: uuid.UUID,
    body: schemas.EstimateIn,
    principal: Principal = Depends(require_permission("portal.damage")),
    db: Session = Depends(get_session),
):
    return service.submit_estimate(db, public_id, user_id=principal.user_id, data=body.model_dump())


@router.get("/portal/accidents/{public_id}/files/{sha256}")
def portal_file(
    public_id: uuid.UUID,
    sha256: str,
    principal: Principal = Depends(require_permission("portal.damage")),
    db: Session = Depends(get_session),
):
    return _file(service.portal_file(db, public_id, sha256, user_id=principal.user_id))


# ------------------------------------------------------------------ the driver app


@router.post("/driver/accidents", response_model=schemas.DriverAccidentOut, status_code=201)
def driver_report(
    body: schemas.DriverAccidentIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.driver_report(db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump())


@router.get("/driver/accidents", response_model=list[schemas.DriverAccidentOut])
def my_accidents(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.for_driver(db, device.employee_id)


@router.post("/driver/accidents/{public_id}/police-report", response_model=schemas.DriverAccidentOut)
def driver_police_report(
    public_id: uuid.UUID,
    body: schemas.PoliceReportIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.driver_police_report(
        db, public_id, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump()
    )
