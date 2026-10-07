import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.org import service as org
from app.modules.violations import schemas, service

router = APIRouter(prefix="/api/v1", tags=["violations"])
SCREEN = [Depends(org.screen("violations"))]


@router.get("/violations", response_model=list[schemas.ViolationOut])
def list_violations(
    status: str | None = None,
    source: schemas.Source | None = None,
    driver_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("violations.view")),
    db: Session = Depends(get_session),
):
    return service.list_violations(
        db,
        status=status,
        source=source,
        driver_public_id=driver_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/violations", response_model=schemas.ViolationOut, status_code=201)
def create(
    body: schemas.ViolationIn,
    principal: Principal = Depends(require_permission("violations.manage")),
    db: Session = Depends(get_session),
):
    return service.create(
        db,
        body.model_dump(),
        actor_user_id=principal.user_id,
        permissions=principal.permissions,
        **principal.scope,
    )


@router.get("/violations/types", response_model=list[schemas.TypeOut])
def list_types(_: Principal = Depends(require_permission("violations.view")), db: Session = Depends(get_session)):
    return service.list_types(db)


@router.post("/violations/types", response_model=schemas.TypeOut, status_code=201)
def create_type(
    body: schemas.TypeIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.save_type(db, body.model_dump(), actor_user_id=principal.user_id)


@router.put("/violations/types/{type_id}", response_model=schemas.TypeOut)
def update_type(
    type_id: int,
    body: schemas.TypeIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.save_type(db, body.model_dump(), type_id=type_id, actor_user_id=principal.user_id)


@router.get("/violations/causes", response_model=list[schemas.CauseOut])
def list_causes(_: Principal = Depends(require_permission("violations.view")), db: Session = Depends(get_session)):
    return service.list_causes(db)


@router.post("/violations/causes", response_model=schemas.CauseOut, status_code=201)
def create_cause(
    body: schemas.CauseIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.save_cause(db, body.model_dump(), actor_user_id=principal.user_id)


@router.put("/violations/causes/{cause_id}", response_model=schemas.CauseOut)
def update_cause(
    cause_id: int,
    body: schemas.CauseIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.save_cause(db, body.model_dump(), cause_id=cause_id, actor_user_id=principal.user_id)


@router.get("/violations/{public_id}", response_model=schemas.ViolationOut)
def get(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("violations.view")),
    db: Session = Depends(get_session),
):
    return service.get(db, public_id, **principal.scope)


@router.get("/violations/{public_id}/files/{sha256}")
def violation_file(
    public_id: uuid.UUID,
    sha256: str,
    principal: Principal = Depends(require_permission("violations.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.violation_file(db, public_id, sha256, **principal.scope))


@router.post("/violations/{public_id}/approve", response_model=schemas.ViolationOut)
def approve(
    public_id: uuid.UUID,
    body: schemas.ApproveIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.approve(
        db, public_id, amount=body.amount, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/violations/{public_id}/exclude", response_model=schemas.ViolationOut)
def exclude(
    public_id: uuid.UUID,
    body: schemas.NoteIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.exclude(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


@router.post("/violations/{public_id}/decide", response_model=schemas.ViolationOut)
def decide(
    public_id: uuid.UUID,
    body: schemas.DecideIn,
    principal: Principal = Depends(require_permission("violations.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_objection(
        db, public_id, uphold=body.uphold, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/driver/violations", response_model=list[schemas.DriverViolationOut], dependencies=SCREEN)
def my_violations(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.for_driver(db, device.employee_id)


@router.post(
    "/driver/violations/{public_id}/objection",
    response_model=schemas.DriverViolationOut,
    status_code=201,
    dependencies=SCREEN,
)
def object_to(
    public_id: uuid.UUID,
    body: schemas.ObjectionIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.object_to(
        db, device.employee_id, public_id, text=body.text, file_sha256=body.file_sha256, device_id=device.device_id
    )
