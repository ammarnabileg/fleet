import json
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import context
from app.core.clock import KUWAIT
from app.core.errors import AppError
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
    company_id: int | None = None,
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
            company_id=company_id,
            before=_jsonable(before),
            after=_jsonable(after),
            ip=context.client_ip.get(),
            request_id=context.request_id.get(),
        )
    )


EXPORT_MAX = 20_000  # rows in one export: narrow the period or the filters past that


def _query(
    *,
    all_companies: bool,
    company_ids: Iterable[int],
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    q = select(AuditEvent).order_by(AuditEvent.id.desc())
    if not all_companies:  # company-limited users see only their companies' events
        q = q.where(AuditEvent.company_id.in_(list(company_ids)))
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if action:  # the action or any under it ("employee" finds "employee.updated"); "_" and "%" are not wildcards
        prefix = action.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + ".%"
        q = q.where(or_(AuditEvent.action == action, AuditEvent.action.like(prefix, escape="\\")))
    if actor_user_id is not None:
        q = q.where(AuditEvent.actor_user_id == actor_user_id)
    if date_from is not None:  # Kuwait days
        q = q.where(AuditEvent.occurred_at >= datetime.combine(date_from, time(0), tzinfo=KUWAIT))
    if date_to is not None:
        q = q.where(AuditEvent.occurred_at < datetime.combine(date_to + timedelta(days=1), time(0), tzinfo=KUWAIT))
    return q


def list_events(db: Session, *, before_id: int | None = None, limit: int = 50, **filters) -> list[AuditEvent]:
    q = _query(**filters).limit(min(limit, 200))
    if before_id:
        q = q.where(AuditEvent.id < before_id)
    return list(db.scalars(q))


def export_events(db: Session, **filters) -> list[AuditEvent]:
    """Every event matching, newest first (BRD FR-AUD-03); refused rather than cut short past EXPORT_MAX."""
    rows = list(db.scalars(_query(**filters).limit(EXPORT_MAX + 1)))
    if len(rows) > EXPORT_MAX:
        raise AppError(422, "export_too_large", max=EXPORT_MAX)
    return rows
