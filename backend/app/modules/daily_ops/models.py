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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Report(Base):
    """A driver's day: orders, cash collected, the screenshot of the platform's daily summary."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("orders_count >= 0", name="orders_count"),
        CheckConstraint("cash_amount >= 0", name="cash_amount"),
        CheckConstraint("status IN ('submitted', 'returned', 'approved', 'rejected')", name="status"),
        CheckConstraint("session >= 1", name="session"),
        Index(
            "reports_one_per_session_idx",
            "employee_id",
            "business_date",
            "session",
            unique=True,
            postgresql_where=text("status <> 'rejected'"),
        ),
        Index("reports_status_idx", "status", "submitted_at"),
        {"schema": "daily_ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    custody_id: Mapped[int | None] = mapped_column(BigInteger)
    vehicle_id: Mapped[int | None] = mapped_column(BigInteger)
    business_date: Mapped[date] = mapped_column(Date)
    # the work session of the day it covers: a driver who starts again after ending the day sends another report
    session: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    orders_count: Mapped[int | None] = mapped_column(Integer)
    cash_amount: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    valid_day: Mapped[bool | None] = mapped_column(Boolean)  # the platform counted the day (its daily summary)
    screenshot_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'submitted'"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    submitted_by_device: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    approved_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last corrected by the driver


class ReportChange(Base):
    """A change to a report, kept with what it was and what it became: the driver's edit before approval, the
    reviewer sending it back, or a change asked for after approval and decided by the reviewer."""

    __tablename__ = "report_changes"
    __table_args__ = (
        CheckConstraint("kind IN ('edit', 'returned', 'request')", name="kind"),
        CheckConstraint("status IN ('applied', 'pending', 'approved', 'rejected')", name="status"),
        CheckConstraint("created_by IS NOT NULL OR created_by_device IS NOT NULL", name="author"),
        Index("report_changes_report_id_idx", "report_id", "id"),
        Index("report_changes_one_pending_idx", "report_id", unique=True, postgresql_where=text("status = 'pending'")),
        {"schema": "daily_ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    report_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("daily_ops.reports.id"))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    before: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    after: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
