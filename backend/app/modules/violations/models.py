import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "violations"}
NUMBER_SEQ = Sequence("violation_number_seq", schema="violations")
SOURCES = "'attendance', 'cash', 'orders', 'complaints', 'accidents', 'tracking'"


class Type(Base):
    """A kind of violation, under one of the six sources (FR-VIO-01), with its usual penalty if any."""

    __tablename__ = "types"
    __table_args__ = (
        CheckConstraint(f"source IN ({SOURCES})", name="source"),
        CheckConstraint("amount >= 0", name="amount"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Cause(Base):
    """A cause outside the driver's responsibility (BR-10): a violation recorded with an active one is excluded."""

    __tablename__ = "causes"
    __table_args__ = (SCHEMA,)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Violation(Base):
    __tablename__ = "violations"
    __table_args__ = (
        CheckConstraint("origin IN ('office', 'alert', 'system')", name="origin"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'excluded', 'objected', 'upheld', 'overturned')", name="status"
        ),
        CheckConstraint("amount >= 0", name="amount"),
        CheckConstraint("status = 'pending' OR reviewed_at IS NOT NULL", name="reviewed"),
        CheckConstraint(
            "status NOT IN ('objected', 'upheld', 'overturned') OR objected_at IS NOT NULL", name="objected"
        ),
        CheckConstraint("status NOT IN ('upheld', 'overturned') OR final_at IS NOT NULL", name="final"),
        Index("violations_auto_key_idx", "auto_key", unique=True, postgresql_where=text("auto_key IS NOT NULL")),
        Index("violations_employee_id_idx", "employee_id", text("occurred_at DESC")),
        Index("violations_status_idx", "status", postgresql_where=text("status IN ('pending', 'objected')")),
        Index(
            "violations_due_idx",
            "objection_deadline",
            postgresql_where=text("status = 'approved' AND deduction_id IS NULL"),
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(Integer, NUMBER_SEQ, server_default=NUMBER_SEQ.next_value(), unique=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("violations.types.id"))
    cause_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("violations.causes.id"))
    vehicle_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(Text)
    evidence_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    origin: Mapped[str] = mapped_column(Text)
    alert_id: Mapped[int | None] = mapped_column(BigInteger)
    auto_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    objection_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    objection: Mapped[str | None] = mapped_column(Text)
    objection_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    objected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_note: Mapped[str | None] = mapped_column(Text)
    final_by: Mapped[int | None] = mapped_column(BigInteger)
    final_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deduction_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class SignalLoss(Base):
    """Each signal loss of a driver during his shift (TRK-M-03), counted toward a violation."""

    __tablename__ = "signal_losses"
    __table_args__ = (
        UniqueConstraint("custody_id", "lost_at", name="signal_losses_custody_id_lost_at_key"),
        Index("signal_losses_employee_id_idx", "employee_id", "lost_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    lost_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    custody_id: Mapped[int] = mapped_column(BigInteger)
