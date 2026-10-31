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
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "approvals"}
PROCESSES = (
    "daily_report",
    "maintenance_request",
    "maintenance_quote",
    "maintenance_invoice",
    "accident_estimate",
    "expense",
    "payroll_run",
    "cash_adjustment",
    "manual_deduction",
)


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "process IN ('daily_report', 'maintenance_request', 'maintenance_quote', 'maintenance_invoice', "
            "'accident_estimate', 'expense', 'payroll_run', 'cash_adjustment', 'manual_deduction')",
            name="process",
        ),
        SCHEMA,
    )

    process: Mapped[str] = mapped_column(Text, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = (
        CheckConstraint("min_amount >= 0", name="min_amount"),
        CheckConstraint("escalate_after_hours > 0", name="escalate_after_hours"),
        CheckConstraint("(role_id IS NULL) <> (user_id IS NULL)", name="approver"),
        CheckConstraint("(escalate_after_hours IS NULL) = (escalate_role_id IS NULL)", name="escalation"),
        SCHEMA,
    )

    process: Mapped[str] = mapped_column(
        Text, ForeignKey("approvals.workflows.process", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[dict] = mapped_column(JSONB)
    role_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.roles.id"))
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.users.id"))
    min_amount: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    escalate_after_hours: Mapped[int | None] = mapped_column(Integer)
    escalate_role_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.roles.id"))


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status"),
        CheckConstraint("(status = 'pending') = (closed_at IS NULL)", name="closed"),
        Index(
            "requests_one_pending",
            "process",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("requests_document_idx", "process", "document_key", "id"),
        Index("requests_status_idx", "status", "step_since"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    process: Mapped[str] = mapped_column(Text)
    document_id: Mapped[int] = mapped_column(BigInteger)
    document_key: Mapped[str] = mapped_column(Text)
    document_ref: Mapped[str] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    steps: Mapped[list] = mapped_column(JSONB)
    current: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    step_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    escalated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_note: Mapped[str | None] = mapped_column(Text)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'rejected', 'escalated')", name="decision"),
        CheckConstraint("decision <> 'rejected' OR reason IS NOT NULL", name="reason"),
        Index("decisions_request_id_idx", "request_id", "id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approvals.requests.id"))
    step: Mapped[int] = mapped_column(SmallInteger)
    decision: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    on_behalf_of: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Delegation(Base):
    __tablename__ = "delegations"
    __table_args__ = (
        CheckConstraint("user_id <> delegate_id", name="self"),
        CheckConstraint("date_to >= date_from", name="range"),
        Index("delegations_delegate_id_idx", "delegate_id", "date_from"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("identity.users.id"))
    delegate_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("identity.users.id"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
