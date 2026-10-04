from sqlalchemy import text
from sqlalchemy.orm import Session

# One relay pass: claim unpublished events without blocking other relays, fan them out to the
# matching subscriptions, mark them published. All in the caller's transaction (tested: T-OUT-01).
_RELAY = text("""
    WITH picked AS (
        SELECT id, event_id, event_type
        FROM integrations.outbox
        WHERE published_at IS NULL
        ORDER BY id
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    ), fanout AS (
        INSERT INTO integrations.deliveries (event_id, subscription_id)
        SELECT p.event_id, s.id
        FROM picked p
        JOIN integrations.subscriptions s ON s.active AND p.event_type = ANY (s.event_types)
        ON CONFLICT DO NOTHING
    )
    UPDATE integrations.outbox o
    SET published_at = now()
    FROM picked p
    WHERE o.id = p.id
    RETURNING o.id
""")


def relay_once(db: Session, limit: int = 100) -> int:
    published = len(db.execute(_RELAY, {"limit": limit}).all())
    db.commit()
    return published


def already_processed(db: Session, consumer: str, event_id) -> bool:
    """Call inside the consumer's transaction: True means a redelivered event, skip it."""
    inserted = db.execute(
        text("""INSERT INTO integrations.processed_events (consumer, event_id)
                                  VALUES (:c, :e) ON CONFLICT DO NOTHING RETURNING 1"""),
        {"c": consumer, "e": event_id},
    ).first()
    return inserted is None
