import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('info', 'warning', 'critical')", name="severity"),
        CheckConstraint("resolution IN ('auto', 'manual')", name="resolution"),
        CheckConstraint("(resolved_at IS NULL) = (resolution IS NULL)", name="resolved"),
        Index("alerts_dedupe_key_idx", "dedupe_key", unique=True, postgresql_where=text("resolved_at IS NULL")),
        Index("alerts_open_idx", "created_at", postgresql_where=text("resolved_at IS NULL")),
        Index("alerts_assigned_to_idx", "assigned_to", postgresql_where=text("resolved_at IS NULL")),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    kind: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    permission: Mapped[str] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(BigInteger)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # seen, not handled
    acknowledged_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last refreshed with new figures
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # handled: no longer open
    resolved_by: Mapped[int | None] = mapped_column(BigInteger)
    resolution: Mapped[str | None] = mapped_column(Text)  # auto: its cause went away; manual: someone handled it
    resolution_note: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[int | None] = mapped_column(BigInteger)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_by: Mapped[int | None] = mapped_column(BigInteger)


class AlertEvent(Base):
    """What people did with an alert: acknowledged, assigned, escalated, resolved."""

    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint("action IN ('acknowledged', 'assigned', 'unassigned', 'escalated', 'resolved')", name="action"),
        Index("alert_events_alert_id_idx", "alert_id", "id"),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("notifications.alerts.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriverNotice(Base):
    __tablename__ = "driver_notices"
    __table_args__ = (
        Index("driver_notices_employee_id_idx", "employee_id", "id"),
        Index(
            "driver_notices_dedupe_idx",
            "employee_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("driver_notices_unpushed_idx", "id", postgresql_where=text("pushed_at IS NULL")),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    kind: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Broadcast(Base):
    """A message from the office to all drivers or a chosen group (ركن الإشعارات), through every channel switched on."""

    __tablename__ = "broadcasts"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'scheduled', 'sending', 'sent', 'cancelled')", name="status"),
        Index("broadcasts_created_at_idx", "created_at"),
        Index("broadcasts_due_idx", "scheduled_at", postgresql_where=text("status = 'scheduled'")),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    title: Mapped[dict] = mapped_column(JSONB)  # {lang: text}
    body: Mapped[dict] = mapped_column(JSONB)
    audience: Mapped[dict] = mapped_column(JSONB)  # {"kind": all|company|platform|on_duty|selected, ...}
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipients: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class BroadcastDelivery(Base):
    """One recipient on one channel: unique, so a retry never sends twice."""

    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'failed', 'skipped')", name="status"),
        CheckConstraint("channel ~ '^[a-z][a-z0-9_]{1,30}$'", name="channel"),
        UniqueConstraint("broadcast_id", "employee_id", "channel"),
        Index("broadcast_deliveries_queued_idx", "channel", "id", postgresql_where=text("status = 'queued'")),
        Index("broadcast_deliveries_whatsapp_idx", "claimed_at", postgresql_where=text("channel = 'whatsapp'")),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("notifications.broadcasts.id", ondelete="CASCADE"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    channel: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    reason: Mapped[str | None] = mapped_column(Text)  # skipped or failed: no_token, no_phone, channel_disabled, ...
    lang: Mapped[str | None] = mapped_column(Text)  # the language it was written in
    provider_ref: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # taken by a sender
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
