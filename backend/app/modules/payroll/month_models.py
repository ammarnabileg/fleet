"""A platform's input fields (daily and monthly), the month's values per driver and where they came from, and the
approved exceptions of a driver's month: what the rule blocks read besides the approved daily reports."""

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "payroll"}


class PlatformForm(Base):
    """What a platform asks: the driver's daily fields and the office's monthly fields, in order."""

    __tablename__ = "platform_forms"
    __table_args__ = SCHEMA

    platform_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payroll.platforms.id", ondelete="CASCADE"), primary_key=True
    )
    daily: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    monthly: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    screenshot: Mapped[bool | None] = mapped_column(Boolean)  # None: the global setting
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonthImport(Base):
    __tablename__ = "month_imports"
    __table_args__ = (
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("format IN ('partner_batches', 'generic')", name="format"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    platform_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.platforms.id"))
    month: Mapped[date] = mapped_column(Date)
    format: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonthValue(Base):
    """A driver's month figure for one of his platform's monthly fields (sub: the batch number, the task type)."""

    __tablename__ = "month_values"
    __table_args__ = (
        UniqueConstraint("platform_id", "month", "employee_id", "key", "sub", name="month_values_platform_id_key"),
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("key ~ '^[a-z][a-z0-9_]{0,39}$'", name="key"),
        CheckConstraint("source IN ('manual', 'import')", name="source"),
        Index("month_values_month_idx", "month", "employee_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    platform_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.platforms.id"))
    month: Mapped[date] = mapped_column(Date)
    key: Mapped[str] = mapped_column(Text)
    sub: Mapped[str] = mapped_column(Text, server_default=text("''"))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    source: Mapped[str] = mapped_column(Text)
    import_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.month_imports.id"))
    set_by: Mapped[int | None] = mapped_column(BigInteger)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonthException(Base):
    """An approved exception of a driver's month (an accepted excuse, a company data error with the corrected
    figures, a day approved as an exception), with its note and who approved it. Cancelled, never deleted."""

    __tablename__ = "month_exceptions"
    __table_args__ = (
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("kind IN ('accepted_excuse', 'company_error', 'exception_day')", name="kind"),
        CheckConstraint("days BETWEEN 0 AND 31", name="days"),
        CheckConstraint("length(btrim(note)) >= 3", name="note"),
        CheckConstraint("(cancelled_at IS NULL) = (cancelled_by IS NULL)", name="cancelled"),
        CheckConstraint(
            "excuses <@ ARRAY['star_day', 'marks', 'lateness', 'absence', 'valid_days']::text[]", name="excuses"
        ),
        Index("month_exceptions_month_idx", "month", "employee_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    month: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)
    days: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    corrections: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    excuses: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))  # what it excuses
    note: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_by: Mapped[int | None] = mapped_column(BigInteger)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_note: Mapped[str | None] = mapped_column(Text)
