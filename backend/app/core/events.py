"""Transactional outbox: an event is written in the same transaction as the change it describes."""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

_INSERT = text("""
    INSERT INTO integrations.outbox (event_type, event_version, aggregate_id, payload)
    VALUES (:event_type, :event_version, :aggregate_id, CAST(:payload AS jsonb))
    RETURNING event_id
""")


def emit(db: Session, event_type: str, aggregate_id: uuid.UUID, payload: dict, version: int = 1) -> uuid.UUID:
    return db.execute(
        _INSERT,
        {
            "event_type": event_type,
            "event_version": version,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(payload, default=str),
        },
    ).scalar_one()
