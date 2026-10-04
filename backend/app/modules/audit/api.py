from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.audit import service
from app.modules.audit.schemas import AuditEventOut
from app.modules.identity.service import Principal, require_permission

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    before_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require_permission("audit.view")),
    db: Session = Depends(get_session),
):
    return service.list_events(
        db,
        **principal.scope,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_id=before_id,
        limit=limit,
    )
