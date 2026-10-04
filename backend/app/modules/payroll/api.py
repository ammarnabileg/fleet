import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.payroll import schemas, service

router = APIRouter(prefix="/api/v1", tags=["payroll"])


@router.get("/deductions", response_model=list[schemas.DeductionOut])
def list_deductions(
    status: Literal["approved", "cancelled"] | None = None,
    employee_id: uuid.UUID | None = None,
    month: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("deductions.view")),
    db: Session = Depends(get_session),
):
    return service.list_deductions(
        db,
        status=status,
        employee_public_id=employee_id,
        month=month,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/deductions/{public_id}/cancel", response_model=schemas.DeductionOut)
def cancel(
    public_id: uuid.UUID,
    body: schemas.CancelIn,
    principal: Principal = Depends(require_permission("deductions.manage")),
    db: Session = Depends(get_session),
):
    return service.cancel(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.get("/driver/deductions", response_model=list[schemas.DeductionOut])
def my_deductions(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """What the driver sees in the app: every live deduction with its monthly installments."""
    return service.for_employee(db, device.employee_id)
