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


class Connection(Base):
    """An external service set up from the control panel: settings in clear, secrets encrypted (core.crypto)."""

    __tablename__ = "connections"
    __table_args__ = (CheckConstraint("kind ~ '^[a-z][a-z0-9_]{1,30}$'", name="kind"), {"schema": "integrations"})

    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    config: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    secrets: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_ok: Mapped[bool | None] = mapped_column(Boolean)
    check_error: Mapped[str | None] = mapped_column(Text)


class MessageLog(Base):
    """One try at sending a message to a driver's phone through WhatsApp or Firebase push, and its outcome as the
    provider gave it. Never the text (a sign-in code must not be kept) and only the recipient's last digits."""

    __tablename__ = "message_log"
    __table_args__ = (
        CheckConstraint("channel IN ('whatsapp', 'push')", name="channel"),
        CheckConstraint("status IN ('accepted', 'failed')", name="status"),
        Index("message_log_channel_idx", "channel", "created_at"),
        Index("message_log_created_at_idx", "created_at"),
        {"schema": "integrations"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)  # evolution | fcm | log | none
    purpose: Mapped[str | None] = mapped_column(Text)  # otp | activation | recovery | claim | notice | ...
    recipient: Mapped[str | None] = mapped_column(Text)  # "…1234"
    status: Mapped[str] = mapped_column(Text)  # accepted: the provider took it (not a delivery receipt) | failed
    error: Mapped[str | None] = mapped_column(Text)
    ref: Mapped[str | None] = mapped_column(Text)  # what was sent: the driver notice's id for a push
    provider_ref: Mapped[str | None] = mapped_column(Text)  # the provider's message id, when it gives one
    attempt: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailOutbox(Base):
    """An email waiting for the SMTP server, or sent: the background job sends what is waiting, a few tries each."""

    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("kind IN ('contact', 'error')", name="kind"),
        Index("email_outbox_pending_idx", "id", postgresql_where=text("sent_at IS NULL AND attempts < 5")),
        Index("email_outbox_dedupe_idx", "dedupe_key", "created_at"),
        {"schema": "integrations"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    reply_to: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
