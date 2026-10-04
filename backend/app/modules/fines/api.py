import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.fines import schemas, service
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission

router = APIRouter(prefix="/api/v1", tags=["fines"])


@router.get("/fines", response_model=list[schemas.FineOut])
def list_fines(
    status: str | None = None,
    unpaid: bool = False,
    no_driver: bool = False,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("fines.view")),
    db: Session = Depends(get_session),
):
    return service.list_fines(
        db,
        status=status,
        unpaid=unpaid,
        no_driver=no_driver,
        vehicle_public_id=vehicle_id,
        driver_public_id=driver_id,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/fines", response_model=schemas.FineOut, status_code=201)
def create(
    body: schemas.FineIn,
    principal: Principal = Depends(require_permission("fines.manage")),
    db: Session = Depends(get_session),
):
    return service.create(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.get("/fines/{public_id}", response_model=schemas.FineOut)
def get(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("fines.view")),
    db: Session = Depends(get_session),
):
    return service.get(db, public_id, **principal.scope)


@router.get("/fines/{public_id}/file")
def fine_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("fines.view")),
    db: Session = Depends(get_session),
):
    info = service.fine_file(db, public_id, **principal.scope)
    return files.response(db, info)


@router.post("/fines/{public_id}/charge", response_model=schemas.FineOut)
def charge(
    public_id: uuid.UUID,
    body: schemas.ChargeIn,
    principal: Principal = Depends(require_permission("deductions.manage")),
    db: Session = Depends(get_session),
):
    """Charging the driver creates an approved deduction: it needs the deductions permission, not the fines one."""
    return service.charge(db, public_id, data=body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.post("/fines/{public_id}/company", response_model=schemas.FineOut)
def company_pays(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("fines.manage")),
    db: Session = Depends(get_session),
):
    return service.company_pays(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/fines/{public_id}/cancel", response_model=schemas.FineOut)
def cancel(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("fines.manage")),
    db: Session = Depends(get_session),
):
    return service.cancel(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/fines/{public_id}/paid", response_model=schemas.FineOut)
def mark_paid(
    public_id: uuid.UUID,
    body: schemas.PaidIn,
    principal: Principal = Depends(require_permission("finance.create")),
    db: Session = Depends(get_session),
):
    return service.mark_paid(
        db, public_id, payment_ref=body.payment_ref, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/driver/fines", response_model=list[schemas.DriverFineOut])
def my_fines(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.for_driver(db, device.employee_id)
