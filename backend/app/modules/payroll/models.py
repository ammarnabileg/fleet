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
SOURCES = ("accident", "fine", "advance", "sim", "other")


class Deduction(Base):
    """What payroll deducts from an employee: a total in equal monthly installments from a start month."""

    __tablename__ = "deductions"
    __table_args__ = (
        CheckConstraint("source_type IN ('accident', 'fine', 'advance', 'sim', 'other')", name="source_type"),
        CheckConstraint("total > 0", name="total"),
        CheckConstraint("installments BETWEEN 1 AND 60", name="installments"),
        CheckConstraint("extract(day FROM start_month) = 1", name="start_month"),
        CheckConstraint("status IN ('approved', 'cancelled')", name="status"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        Index(
            "deductions_one_per_source_idx",
            "source_type",
            "source_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled' AND source_id IS NOT NULL"),
        ),
        Index("deductions_employee_id_idx", "employee_id", "start_month"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    installments: Mapped[int] = mapped_column(SmallInteger)
    start_month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'approved'"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_by: Mapped[int | None] = mapped_column(BigInteger)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class Platform(Base):
    """A delivery platform: its pay rule and its salary sheet (columns in order with the client's headers)."""

    __tablename__ = "platforms"
    __table_args__ = (
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,30}$'", name="code"),
        CheckConstraint("driver_fields <@ ARRAY['valid_days', 'orders', 'hours']::text[]", name="driver_fields"),
        CheckConstraint("per_order >= 0", name="per_order"),
        CheckConstraint("per_hour >= 0", name="per_hour"),
        CheckConstraint("per_valid_day >= 0", name="per_valid_day"),
        CheckConstraint("invalid_days IN ('none', 'daily_wage', 'fixed')", name="invalid_days"),
        CheckConstraint("invalid_day_amount >= 0", name="invalid_day_amount"),
        CheckConstraint("day_divisor BETWEEN 1 AND 31", name="day_divisor"),
        CheckConstraint("invalid_days <> 'fixed' OR invalid_day_amount IS NOT NULL", name="fixed"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    driver_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    pay_basic: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    per_order: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    per_hour: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    per_valid_day: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    invalid_days: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    invalid_day_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    day_divisor: Mapped[int] = mapped_column(SmallInteger, server_default=text("30"))
    columns: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Statement(Base):
    """A platform's figures for a driver's month: sent by the driver with screenshots, or entered by the office."""

    __tablename__ = "statements"
    __table_args__ = (
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("status IN ('submitted', 'approved', 'rejected')", name="status"),
        CheckConstraint("working_days BETWEEN 0 AND 31", name="working_days"),
        CheckConstraint("valid_days BETWEEN 0 AND 31", name="valid_days"),
        CheckConstraint("orders >= 0", name="orders"),
        CheckConstraint("hours BETWEEN 0 AND 744", name="hours"),
        CheckConstraint("bonus >= 0", name="bonus"),
        CheckConstraint("tips >= 0", name="tips"),
        CheckConstraint("cancelled_orders >= 0", name="cancelled_orders"),
        CheckConstraint("platform_deductions >= 0", name="platform_deductions"),
        CheckConstraint("late >= 0", name="late"),
        CheckConstraint("cash_shortage >= 0", name="cash_shortage"),
        CheckConstraint("status <> 'rejected' OR review_note IS NOT NULL", name="rejected"),
        CheckConstraint("submitted_by_device IS NOT NULL OR submitted_by_user IS NOT NULL", name="source"),
        Index(
            "statements_one_per_month_idx",
            "employee_id",
            "month",
            unique=True,
            postgresql_where=text("status <> 'rejected'"),
        ),
        Index("statements_month_idx", "month", "status"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    platform_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.platforms.id"))
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'submitted'"))
    declared: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    working_days: Mapped[int | None] = mapped_column(SmallInteger)
    valid_days: Mapped[int | None] = mapped_column(SmallInteger)
    orders: Mapped[int | None] = mapped_column(Integer)
    hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    bonus: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    tips: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    cancelled_orders: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    platform_deductions: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    late: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    cash_shortage: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_by_device: Mapped[int | None] = mapped_column(BigInteger)
    submitted_by_user: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class StatementFile(Base):
    __tablename__ = "statement_files"
    __table_args__ = SCHEMA

    statement_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.statements.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger)


class Run(Base):
    """One payroll per company and month: a draft recomputed at will, then approved (locked), then paid."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("status IN ('draft', 'approved', 'paid')", name="status"),
        CheckConstraint("cap_base IN ('basic', 'gross')", name="cap_base"),
        CheckConstraint("status = 'draft' OR approved_at IS NOT NULL", name="approved"),
        CheckConstraint("status <> 'paid' OR paid_at IS NOT NULL", name="paid"),
        UniqueConstraint("company_id", "month", name="runs_company_id_key"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    cap_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    cap_base: Mapped[str] = mapped_column(Text)
    totals: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    prepared_by: Mapped[int] = mapped_column(BigInteger)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[int | None] = mapped_column(BigInteger)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[int | None] = mapped_column(BigInteger)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_ref: Mapped[str | None] = mapped_column(Text)
    reopened: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="lines_run_id_key"),
        Index("lines_employee_id_idx", "employee_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.runs.id", ondelete="CASCADE"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    platform_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.platforms.id"))
    statement_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.statements.id"))
    cells: Mapped[dict] = mapped_column(JSONB)  # every salary-sheet column's value, by column code
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    net: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))


class LineDeduction(Base):
    """What one installment-based deduction asked for and actually took in a line's month."""

    __tablename__ = "line_deductions"
    __table_args__ = (
        CheckConstraint("deducted >= 0", name="deducted"),
        Index("line_deductions_deduction_id_idx", "deduction_id"),
        SCHEMA,
    )

    line_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payroll.lines.id", ondelete="CASCADE"), primary_key=True
    )
    deduction_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.deductions.id"), primary_key=True)
    due: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    deducted: Mapped[Decimal] = mapped_column(Numeric(12, 3))
