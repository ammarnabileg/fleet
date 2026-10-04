import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.tracking import schemas, service

router = APIRouter(prefix="/api/v1", tags=["tracking"])


@router.post("/driver/positions", response_model=schemas.BatchOut)
def upload_positions(
    body: schemas.BatchIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.ingest(db, device, sent_at=body.sent_at, points=[p.model_dump() for p in body.points])


@router.post("/driver/status", response_model=schemas.HeartbeatOut)
def heartbeat(
    body: schemas.HeartbeatIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.heartbeat(db, device, body.model_dump(mode="json"))


@router.get("/tracking/live", response_model=list[schemas.LiveVehicle])
def live(principal: Principal = Depends(require_permission("tracking.live")), db: Session = Depends(get_session)):
    return service.live_snapshot(db, **principal.scope)


def _live_scope(
    principal: Principal = Depends(require_permission("tracking.live")), db: Session = Depends(get_session)
) -> set[int]:
    return service.company_scope(db, **principal.scope)


@router.get("/tracking/live/stream")
async def live_stream(company_ids: set[int] = Depends(_live_scope)):
    """Server-sent events: one "position" event per new vehicle position in the user's companies.
    Asynchronous: an open map holds no worker thread and no database connection."""
    return StreamingResponse(
        service.live_events(company_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/tracking/route", response_model=schemas.RouteOut)
def route(
    vehicle_id: uuid.UUID | None = None,
    custody_id: uuid.UUID | None = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    principal: Principal = Depends(require_permission("tracking.history")),
    db: Session = Depends(get_session),
):
    return service.route(
        db, vehicle_public_id=vehicle_id, custody_public_id=custody_id, start=start, end=end, **principal.scope
    )
