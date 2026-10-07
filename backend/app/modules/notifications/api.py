import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.i18n import service as i18n
from app.modules.identity.service import DevicePrincipal, Principal, get_principal, require_device
from app.modules.notifications import schemas, service

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/alerts", response_model=list[schemas.AlertOut])
def list_alerts(
    open: bool = True,
    kind: str | None = None,
    before: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    """Only the alerts of the permissions the user holds, within the user's companies."""
    return service.list_alerts(
        db,
        permissions=principal.permissions,
        lang=i18n.negotiate(db, principal.locale, accept_language),
        open_only=open,
        kind=kind,
        before=before,
        limit=limit,
        **principal.scope,
    )


@router.post("/alerts/{public_id}/ack", status_code=204)
def acknowledge(
    public_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)
):
    service.acknowledge(
        db, public_id, actor_user_id=principal.user_id, permissions=principal.permissions, **principal.scope
    )


@router.get("/driver/notifications", response_model=schemas.DriverNoticesOut)
def driver_notices(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    accept_language: Annotated[str | None, Header()] = None,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """What the driver was told: receipts, decisions on his reports and requests, deductions, payslips, documents."""
    return service.driver_notices(db, device.employee_id, lang=i18n.negotiate(db, None, accept_language), limit=limit)


@router.post("/driver/notifications/read", response_model=schemas.ReadOut)
def read_notices(
    body: schemas.ReadIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return {"count": service.mark_read(db, device.employee_id, body.ids)}
