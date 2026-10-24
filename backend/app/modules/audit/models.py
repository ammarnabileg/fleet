from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditEvent(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'system', 'device', 'service')", name="actor_type"),
        Index("events_entity_idx", "entity_type", "entity_id", "id"),
        Index("events_occurred_at_idx", "occurred_at"),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_type: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(BigInteger)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    device: Mapped[str | None] = mapped_column(Text)  # the browser, or the driver app with the phone model
    comment: Mapped[str | None] = mapped_column(Text)  # the reason or note given with the action
