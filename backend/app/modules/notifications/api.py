import uuid
from typing import Annotated, Literal

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
    open: bool | None = None,
    status: Literal["open", "new", "seen", "resolved", "all"] | None = None,
    severity: Literal["critical", "warning", "info"] | None = None,
    kind: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    assigned: Annotated[str | None, Query(max_length=40)] = None,
    sort: Literal["newest", "severity"] = "newest",
    before: AwareDatetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    """Only the alerts of the permissions the user holds, within the user's companies. status: open (default: not
    handled yet), new (seen by nobody), seen, resolved or all; open=false (older clients) is all."""
    if status is None:
        status = "all" if open is False else "open"
    return service.list_alerts(
        db,
        permissions=principal.permissions,
        lang=i18n.negotiate(db, principal.locale, accept_language),
        status=status,
        severity=severity,
        kind=kind,
        q=q,
        since=since,
        until=until,
        assigned=assigned,
        user_id=principal.user_id,
        sort=sort,
        before=before,
        offset=offset,
        limit=limit,
        **principal.scope,
    )


@router.get("/alerts/summary", response_model=schemas.AlertSummary)
def alerts_summary(
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    """Polled by the panel: open counts, the unseen ones and the user's own, and the newest open alert."""
    return service.summary(
        db,
        permissions=principal.permissions,
        lang=i18n.negotiate(db, principal.locale, accept_language),
        user_id=principal.user_id,
        **principal.scope,
    )


@router.get("/alerts/{public_id}", response_model=schemas.AlertDetail)
def alert_detail(
    public_id: uuid.UUID,
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    return service.detail(
        db,
        public_id,
        lang=i18n.negotiate(db, principal.locale, accept_language),
        permissions=principal.permissions,
        **principal.scope,
    )


@router.get("/alerts/{public_id}/handlers", response_model=list[schemas.UserRef])
def alert_handlers(
    public_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)
):
    """Who the alert may be assigned or escalated to: the users who would see it themselves."""
    return service.handlers(db, public_id, permissions=principal.permissions, **principal.scope)


@router.post("/alerts/{public_id}/ack", status_code=204)
def acknowledge(
    public_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)
):
    """Seen: the alert stays open until handled."""
    service.acknowledge(
        db, public_id, actor_user_id=principal.user_id, permissions=principal.permissions, **principal.scope
    )


@router.post("/alerts/{public_id}/resolve", status_code=204)
def resolve(
    public_id: uuid.UUID,
    body: schemas.ResolveIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    """Handled, and how: the alert closes."""
    service.resolve_by_user(
        db,
        public_id,
        note=body.note.strip(),
        actor_user_id=principal.user_id,
        permissions=principal.permissions,
        **principal.scope,
    )


@router.post("/alerts/{public_id}/assign", status_code=204)
def assign(
    public_id: uuid.UUID,
    body: schemas.AssignIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    service.assign(
        db,
        public_id,
        user_public_id=body.user_id,
        note=(body.note or "").strip() or None,
        escalate=False,
        actor_user_id=principal.user_id,
        permissions=principal.permissions,
        **principal.scope,
    )


@router.post("/alerts/{public_id}/escalate", status_code=204)
def escalate(
    public_id: uuid.UUID,
    body: schemas.EscalateIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    service.assign(
        db,
        public_id,
        user_public_id=body.user_id,
        note=body.note.strip(),
        escalate=True,
        actor_user_id=principal.user_id,
        permissions=principal.permissions,
        **principal.scope,
    )


@router.get("/driver/notifications", response_model=schemas.DriverNoticesOut)
def driver_notices(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    accept_language: Annotated[str | None, Header()] = None,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """What the driver was told: receipts, decisions on his reports and requests, deductions, payslips, documents."""
    return service.driver_notices(db, device.employee_id, lang=i18n.driver_lang(db, accept_language), limit=limit)


@router.post("/driver/notifications/read", response_model=schemas.ReadOut)
def read_notices(
    body: schemas.ReadIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return {"count": service.mark_read(db, device.employee_id, body.ids)}


@router.get("/driver/broadcast-images/{sha256}")
def driver_broadcast_image(
    sha256: str, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    """The picture of a broadcast in the driver's inbox (the app keeps it once downloaded)."""
    return service.driver_image(db, device.employee_id, sha256)
