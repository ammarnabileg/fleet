import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import context
from app.modules.audit.models import AuditEvent


def _jsonable(value: Any) -> Any:
    return None if value is None else json.loads(json.dumps(value, default=str))


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    actor_user_id: int | None = None,
    actor_type: str | None = None,
    branch_id: int | None = None,
    before: Any = None,
    after: Any = None,
) -> None:
    """Adds an audit event to the caller's transaction: it is committed, or rolled back, with the change itself."""
    db.add(
        AuditEvent(
            actor_type=actor_type or ("user" if actor_user_id else "system"),
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            branch_id=branch_id,
            before=_jsonable(before),
            after=_jsonable(after),
            ip=context.client_ip.get(),
            request_id=context.request_id.get(),
        )
    )


def list_events(
    db: Session,
    *,
    all_branches: bool,
    branch_ids: Iterable[int],
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> list[AuditEvent]:
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit, 200))
    if not all_branches:  # branch-scoped users see only their branches' events
        q = q.where(AuditEvent.branch_id.in_(list(branch_ids)))
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if action:
        q = q.where(or_(AuditEvent.action == action, AuditEvent.action.like(f"{action}.%")))
    if before_id:
        q = q.where(AuditEvent.id < before_id)
    return list(db.scalars(q))
