import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OutboxEvent(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("outbox_unpublished_idx", "id", postgresql_where=text("published_at IS NULL")),
        {"schema": "integrations"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    event_type: Mapped[str] = mapped_column(Text)
    event_version: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID)
    payload: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = {"schema": "integrations"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    target_url: Mapped[str | None] = mapped_column(Text)
    event_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'delivered', 'dead')", name="status"),
        Index("deliveries_next_attempt_at_idx", "next_attempt_at", postgresql_where=text("status = 'pending'")),
        {"schema": "integrations"},
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("integrations.outbox.event_id"), primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("integrations.subscriptions.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = {"schema": "integrations"}

    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
