import uuid

from sqlalchemy import text

from app.core.events import emit
from app.modules.integrations import service


def test_relay_fans_out_once_and_consumers_dedupe(db):
    db.execute(
        text(
            "INSERT INTO integrations.subscriptions (name, event_types) VALUES "
            "('internal:notifications', '{cash.shortage.posted}'), ('hr:payroll', '{payroll_input.approved}')"
        )
    )
    e1 = emit(db, "cash.shortage.posted", uuid.uuid4(), {"amount": "2.000"})
    emit(db, "payroll_input.approved", uuid.uuid4(), {})
    emit(db, "nobody.listens", uuid.uuid4(), {})
    db.commit()
    assert service.relay_once(db) == 3
    assert service.relay_once(db) == 0
    rows = db.execute(
        text(
            "SELECT s.name, d.status FROM integrations.deliveries d "
            "JOIN integrations.subscriptions s ON s.id = d.subscription_id ORDER BY s.name"
        )
    ).all()
    assert rows == [("hr:payroll", "pending"), ("internal:notifications", "pending")]
    assert service.already_processed(db, "notifications", e1) is False
    assert service.already_processed(db, "notifications", e1) is True
