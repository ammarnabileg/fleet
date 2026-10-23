import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "attendance"}
MARK_KINDS = ("absence", "leave", "rest", "no_vehicle", "system_fault")


class LeaveType(Base):
    """A kind of leave and its rules; seeded with the labour law's defaults (to review with HR/legal counsel)."""

    __tablename__ = "leave_types"
    __table_args__ = (
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,30}$'", name="code"),
        CheckConstraint("tier_period IN ('occurrence', 'service_year')", name="tier_period"),
        CheckConstraint("counts IN ('calendar', 'working')", name="counts"),
        CheckConstraint("eligible_gender IN ('male', 'female')", name="eligible_gender"),
        SCHEMA,
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[dict] = mapped_column(JSONB)
    legal_ref: Mapped[str | None] = mapped_column(Text)
    tiers: Mapped[list] = mapped_column(JSONB)  # [{days (None: no end), pay_percent}], applied in order
    tier_period: Mapped[str] = mapped_column(Text, server_default=text("'occurrence'"))
    max_per_occurrence: Mapped[int | None] = mapped_column(Integer)
    max_per_year: Mapped[int | None] = mapped_column(Integer)  # per service year (annual: the yearly entitlement)
    max_per_service: Mapped[int | None] = mapped_column(Integer)
    min_service_months: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    once_per_service: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    requires_attachment: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    eligible_gender: Mapped[str | None] = mapped_column(Text)
    counts: Mapped[str] = mapped_column(Text, server_default=text("'calendar'"))
    accrues: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    office_may_pay: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    driver_may_request: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Leave(Base):
    """A leave over a range of days: pending, then approved or rejected (with a note), or cancelled (with a reason)."""

    __tablename__ = "leaves"
    __table_args__ = (
        CheckConstraint("source IN ('office', 'driver')", name="source"),
        CheckConstraint("created_by IS NOT NULL OR created_by_device IS NOT NULL", name="creator"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status"),
        CheckConstraint("date_to >= date_from", name="range"),
        CheckConstraint("(status = 'pending') = (decided_at IS NULL) OR status = 'cancelled'", name="decided"),
        CheckConstraint("status <> 'rejected' OR decision_note IS NOT NULL", name="rejected"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        Index("leaves_employee_id_idx", "employee_id", "date_from"),
        Index("leaves_status_idx", "status", "date_from"),
        Index(
            "leaves_followup_idx",
            "followup_from",
            postgresql_where=text("status IN ('pending', 'approved') AND followed_up_at IS NULL"),
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text, ForeignKey("attendance.leave_types.code"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    note: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    counted_days: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    split: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'"))  # [{days, pay_percent}] over counted days
    paid_override: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # the office made it paid
    rules_overridden: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source: Mapped[str] = mapped_column(Text, server_default=text("'office'"))
    client_ref: Mapped[uuid.UUID | None] = mapped_column(UUID, unique=True)
    followup_from: Mapped[date] = mapped_column(Date)
    followed_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followed_up_by: Mapped[int | None] = mapped_column(BigInteger)


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
