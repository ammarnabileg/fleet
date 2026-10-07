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
        Index("alerts_dedupe_key_idx", "dedupe_key", unique=True, postgresql_where=text("acknowledged_at IS NULL")),
        Index("alerts_open_idx", "created_at", postgresql_where=text("acknowledged_at IS NULL")),
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
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[int | None] = mapped_column(BigInteger)


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
