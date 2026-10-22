import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
