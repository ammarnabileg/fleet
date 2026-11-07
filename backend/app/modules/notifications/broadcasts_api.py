"""The broadcasts page (ركن الإشعارات): compose, preview who each channel reaches, send or schedule, history."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, require_permission
from app.modules.notifications import broadcasts, schemas

router = APIRouter(prefix="/api/v1", tags=["broadcasts"])
VIEW, SEND = "broadcasts.view", "broadcasts.send"


@router.get("/broadcasts/channels")
def channels(_: Principal = Depends(require_permission(VIEW)), db: Session = Depends(get_session)):
    """The channels and whether each is switched on (a channel is switched on in the integrations page only)."""
    return broadcasts.channel_states(db)


@router.post("/broadcasts/preview")
def preview(
    body: schemas.BroadcastPreviewIn,
    principal: Principal = Depends(require_permission(SEND)),
    db: Session = Depends(get_session),
):
    """How many drivers each channel will reach, and why the others will not, before sending."""
    return broadcasts.preview(
        db, audience=body.audience.model_dump(mode="json"), channels=body.channels, **principal.scope
    )


@router.post("/broadcasts", response_model=schemas.BroadcastOut, status_code=201)
def create(
    body: schemas.BroadcastIn,
    principal: Principal = Depends(require_permission(SEND)),
    db: Session = Depends(get_session),
):
    return broadcasts.create(
        db,
        title=body.title,
        body=body.body,
        audience=body.audience.model_dump(mode="json"),
        channels=body.channels,
        scheduled_at=body.scheduled_at,
        send=body.send,
        style=body.style,
        layout=body.layout,
        image=body.image,
        action=body.action.model_dump() if body.action else None,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.get("/broadcasts/images/{sha256}")
def image(sha256: str, _: Principal = Depends(require_permission(VIEW)), db: Session = Depends(get_session)):
    """A card's picture, for the panel's preview and history (stored JPEG or PNG only)."""
    from app.core.errors import AppError
    from app.modules.files import service as files

    info = files.get(db, sha256)
    if info.content_type not in files.IMAGES:
        raise AppError(404, "file_not_found")
    return files.response(db, info)


@router.get("/broadcasts", response_model=list[schemas.BroadcastOut])
def list_(
    status: Literal["draft", "scheduled", "sending", "sent", "cancelled"] | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: Principal = Depends(require_permission(VIEW)),
    db: Session = Depends(get_session),
):
    return broadcasts.list_broadcasts(db, status=status, q=q, limit=limit, offset=offset)


@router.get("/broadcasts/{public_id}", response_model=schemas.BroadcastOut)
def get(public_id: uuid.UUID, _: Principal = Depends(require_permission(VIEW)), db: Session = Depends(get_session)):
    return broadcasts.detail(db, public_id)


@router.get("/broadcasts/{public_id}/deliveries", response_model=list[schemas.BroadcastDeliveryOut])
def deliveries(
    public_id: uuid.UUID,
    status: Literal["queued", "sent", "failed", "skipped"] | None = None,
    channel: Annotated[str | None, Query(max_length=31)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: Principal = Depends(require_permission(VIEW)),
    db: Session = Depends(get_session),
):
    return broadcasts.deliveries(db, public_id, status=status, channel=channel, limit=limit, offset=offset)


@router.post("/broadcasts/{public_id}/send", response_model=schemas.BroadcastOut)
def send(
    public_id: uuid.UUID, principal: Principal = Depends(require_permission(SEND)), db: Session = Depends(get_session)
):
    return broadcasts.send_draft(db, public_id, actor_user_id=principal.user_id)


@router.post("/broadcasts/{public_id}/cancel", response_model=schemas.BroadcastOut)
def cancel(
    public_id: uuid.UUID, principal: Principal = Depends(require_permission(SEND)), db: Session = Depends(get_session)
):
    return broadcasts.cancel(db, public_id, actor_user_id=principal.user_id)


@router.post("/broadcasts/{public_id}/resend", response_model=schemas.BroadcastOut)
def resend(
    public_id: uuid.UUID,
    body: schemas.ResendIn,
    principal: Principal = Depends(require_permission(SEND)),
    db: Session = Depends(get_session),
):
    """The failed deliveries sent again (all channels, or one)."""
    return broadcasts.resend_failed(db, public_id, actor_user_id=principal.user_id, channel=body.channel)
