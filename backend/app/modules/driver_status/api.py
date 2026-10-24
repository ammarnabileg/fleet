import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.driver_status import schemas, service
from app.modules.i18n import service as i18n
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission

router = APIRouter(prefix="/api/v1", tags=["driver_status"])


@router.get("/driver/live-status")
def live_status(
    config_version: Annotated[int | None, Query(ge=0)] = None,
    accept_language: Annotated[str | None, Header()] = None,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """The driver's shift, car, tracking and alerts, as separate states; the templates when the app's cached
    config_version is not the current one."""
    return service.for_driver(db, device, lang=i18n.driver_lang(db, accept_language), config_version=config_version)


@router.post("/driver/contact-requests/{public_id}/ack")
def acknowledge(
    public_id: uuid.UUID,
    body: schemas.AckIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.acknowledge(db, device, public_id, client_ref=body.client_ref)


@router.get("/driver-status")
def drivers(
    accept_language: Annotated[str | None, Header()] = None,
    principal: Principal = Depends(require_permission("tracking.live")),
    db: Session = Depends(get_session),
):
    return service.drivers(db, lang=i18n.negotiate(db, principal.locale, accept_language), **principal.scope)


@router.get("/driver-status/contact-requests")
def contact_requests(
    status: Literal["open", "acknowledged", "closed", "active", "all"] = "active",
    principal: Principal = Depends(require_permission("tracking.live")),
    db: Session = Depends(get_session),
):
    return service.list_requests(db, status=status, **principal.scope)


@router.post("/driver-status/contact-requests", status_code=201)
def create_contact_request(
    body: schemas.ContactIn,
    principal: Principal = Depends(require_permission("tracking.live")),
    db: Session = Depends(get_session),
):
    return service.create_request(
        db,
        driver_public_id=body.driver_id,
        message=body.message,
        reason=body.reason or None,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/driver-status/contact-requests/{public_id}/close")
def close_contact_request(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("tracking.live")),
    db: Session = Depends(get_session),
):
    return service.close_request(db, public_id, actor_user_id=principal.user_id, **principal.scope)


@router.get("/driver-status/templates")
def templates(_: Principal = Depends(require_permission("settings.view")), db: Session = Depends(get_session)):
    return service.manage(db)


@router.post("/driver-status/templates/preview")
def preview(
    body: schemas.PreviewIn,
    _: Principal = Depends(require_permission("settings.view")),
    db: Session = Depends(get_session),
):
    return service.preview(db, body.code, body.template.model_dump(), body.lang, body.values)


@router.put("/driver-status/templates/{code}")
def publish(
    code: str,
    body: schemas.PublishIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.publish(
        db,
        code,
        body.template.model_dump(),
        expected_version=body.config_version,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/driver-status/templates/rollback")
def rollback(
    body: schemas.RollbackIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.rollback(db, expected_version=body.config_version, actor_user_id=principal.user_id)
