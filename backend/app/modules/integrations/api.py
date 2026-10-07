from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity import service as identity
from app.modules.identity.service import Principal, require_permission
from app.modules.integrations import schemas, service

router = APIRouter(prefix="/api/v1", tags=["integrations"])
MANAGE = "integrations.manage"


def _status(db: Session, kind: str) -> dict:
    if kind == "storage":
        return {"files": files.counts(db)}  # files on the disk are copied to R2 in the background once it is on
    if kind == "push":
        return {"phones": identity.push_phones(db)}  # drivers' phones registered for push
    return {"server_mode": get_settings().messaging_provider}  # what is used while WhatsApp is off here


@router.get("/integrations/connections", response_model=list[schemas.ConnectionOut])
def list_connections(_: Principal = Depends(require_permission(MANAGE)), db: Session = Depends(get_session)):
    """External services and their settings. Secrets are never returned: only whether each is set."""
    return [service.connection_out(db, kind, _status(db, kind)) for kind in schemas.KINDS]


@router.put("/integrations/connections/{kind}", response_model=schemas.ConnectionOut)
def save_connection(
    kind: str,
    body: schemas.ConnectionIn,
    principal: Principal = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_session),
):
    """Saves the settings. Switching a service on tries it first (a write to the bucket, a call to the Evolution
    API); if the try fails, nothing is saved and the error says why."""
    service.save(
        db,
        kind,
        version=body.version,
        config=body.config,
        secrets=body.secrets,
        actor_user_id=principal.user_id,
        r2_files=files.counts(db)["r2"] if kind == "storage" else 0,
    )
    return service.connection_out(db, kind, _status(db, kind))


@router.post("/integrations/connections/{kind}/check", response_model=schemas.ConnectionOut)
def check_connection(kind: str, _: Principal = Depends(require_permission(MANAGE)), db: Session = Depends(get_session)):
    """Tries the saved settings now and records the answer."""
    service.check(db, kind)
    return service.connection_out(db, kind, _status(db, kind))
