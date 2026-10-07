import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "attendance"}
LEAVE_KINDS = ("annual", "sick", "emergency", "unpaid", "other")
MARK_KINDS = ("absence", "leave", "rest", "no_vehicle", "system_fault")


class Leave(Base):
    """A leave over a range of days: pending, then approved or rejected (with a note), or cancelled (with a reason)."""

    __tablename__ = "leaves"
    __table_args__ = (
        CheckConstraint("kind IN ('annual', 'sick', 'emergency', 'unpaid', 'other')", name="kind"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status"),
        CheckConstraint("date_to >= date_from", name="range"),
        CheckConstraint("(status = 'pending') = (decided_at IS NULL) OR status = 'cancelled'", name="decided"),
        CheckConstraint("status <> 'rejected' OR decision_note IS NOT NULL", name="rejected"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        Index("leaves_employee_id_idx", "employee_id", "date_from"),
        Index("leaves_status_idx", "status", "date_from"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    note: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class DayMark(Base):
    """What HR decided a day without a start of day was. One per employee and day; a change replaces it."""

    __tablename__ = "day_marks"
    __table_args__ = (
        CheckConstraint("kind IN ('absence', 'leave', 'rest', 'no_vehicle', 'system_fault')", name="kind"),
        Index("day_marks_day_idx", "day"),
        SCHEMA,
    )

    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    marked_by: Mapped[int] = mapped_column(BigInteger)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
