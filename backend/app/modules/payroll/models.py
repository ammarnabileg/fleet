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
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status"),
        CheckConstraint("status NOT IN ('cancelled', 'rejected') OR cancel_reason IS NOT NULL", name="cancelled"),
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
    # the day it enters the books when not the day it was made (approved after that day was closed)
    books_date: Mapped[date | None] = mapped_column(Date)
    cancelled_by: Mapped[int | None] = mapped_column(BigInteger)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class Platform(Base):
    """A delivery platform: its pay rule and its salary sheet (columns in order with the client's headers)."""

    __tablename__ = "platforms"
    __table_args__ = (
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,30}$'", name="code"),
        CheckConstraint("driver_fields <@ ARRAY['valid_days', 'orders', 'hours']::text[]", name="driver_fields"),
        CheckConstraint("daily_fields <@ ARRAY['orders', 'cash', 'valid_day']::text[]", name="daily_fields"),
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
    driver_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))  # monthly statement
    daily_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{orders,cash}'"))  # daily report
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
        CheckConstraint("batch_level BETWEEN 1 AND 20", name="batch_level"),
        CheckConstraint("attendance_marks >= 0", name="attendance_marks"),
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
    # monthly facts a scheme needs, from the platform's partner report (the reviewer enters them)
    batch_level: Mapped[int | None] = mapped_column(SmallInteger)
    attendance_marks: Mapped[int | None] = mapped_column(SmallInteger)
    star_day_failed: Mapped[bool | None] = mapped_column(Boolean)
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
    scheme_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.schemes.id"))
    scheme_version: Mapped[int | None] = mapped_column(Integer)  # the scheme's terms version the month was paid on
    breakdown: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))  # how the scheme got the pay


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


class Scheme(Base):
    """A pay scheme a platform offers (per order, by batch level, base price with tier bonuses and penalties): its
    calculator and its numbers. The numbers change by version, each from a month (SchemeVersion); the columns here
    and the scheme's steps hold the latest version, a run reads the version of its own month."""

    __tablename__ = "schemes"
    __table_args__ = (
        UniqueConstraint("platform_id", "code", name="schemes_platform_id_key"),
        CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,30}$'", name="code"),
        CheckConstraint("calculator IN ('platform_rates', 'per_order', 'batch', 'tiered_target')", name="calculator"),
        CheckConstraint("per_order >= 0", name="per_order"),
        CheckConstraint("target_orders >= 0", name="target_orders"),
        CheckConstraint("required_valid_days BETWEEN 0 AND 31", name="required_valid_days"),
        CheckConstraint("missing_order_rate >= 0", name="missing_order_rate"),
        CheckConstraint("reduced_rate >= 0", name="reduced_rate"),
        CheckConstraint(
            "company_covers <@ ARRAY['maintenance', 'housing', 'gas', 'sim']::text[]", name="company_covers"
        ),
        CheckConstraint(
            "(calculator NOT IN ('per_order', 'tiered_target') OR per_order IS NOT NULL) AND "
            "(calculator <> 'tiered_target' OR reduced_rate IS NOT NULL)",
            name="rates",
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    platform_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.platforms.id"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[dict | None] = mapped_column(JSONB)
    calculator: Mapped[str] = mapped_column(Text)
    per_order: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    target_orders: Mapped[int] = mapped_column(Integer, server_default=text("420"))
    required_valid_days: Mapped[int] = mapped_column(SmallInteger, server_default=text("28"))
    missing_order_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    reduced_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    bonus_when_reduced: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    marks_when_reduced: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    floor_at_zero: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    company_covers: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    driver_selectable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class SchemeVersion(Base):
    """A scheme's terms from a month on, until the next version's month (the first version also covers any month
    before it). A run pays each month on its own month's version, so a change never reaches a month already paid."""

    __tablename__ = "scheme_versions"
    __table_args__ = (
        UniqueConstraint("scheme_id", "version_no", name="scheme_versions_scheme_id_key"),
        UniqueConstraint("scheme_id", "effective_month", name="scheme_versions_month_key"),
        CheckConstraint("version_no >= 1", name="version_no"),
        CheckConstraint("extract(day FROM effective_month) = 1", name="effective_month"),
        CheckConstraint("per_order >= 0", name="per_order"),
        CheckConstraint("target_orders >= 0", name="target_orders"),
        CheckConstraint("required_valid_days BETWEEN 0 AND 31", name="required_valid_days"),
        CheckConstraint("missing_order_rate >= 0", name="missing_order_rate"),
        CheckConstraint("reduced_rate >= 0", name="reduced_rate"),
        CheckConstraint(
            "company_covers <@ ARRAY['maintenance', 'housing', 'gas', 'sim']::text[]", name="company_covers"
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scheme_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.schemes.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    effective_month: Mapped[date] = mapped_column(Date)
    per_order: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    target_orders: Mapped[int] = mapped_column(Integer)
    required_valid_days: Mapped[int] = mapped_column(SmallInteger)
    missing_order_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    reduced_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    bonus_when_reduced: Mapped[bool] = mapped_column(Boolean)
    marks_when_reduced: Mapped[bool] = mapped_column(Boolean)
    floor_at_zero: Mapped[bool] = mapped_column(Boolean)
    company_covers: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    steps: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))  # [{kind, threshold, amount}]
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemeStep(Base):
    """A list-shaped rule of a scheme: a threshold and what it gives (a batch level's price per order, a tier's
    bonus from a number of orders, a deduction from a number of attendance marks, or the reduced price)."""

    __tablename__ = "scheme_steps"
    __table_args__ = (
        CheckConstraint("kind IN ('batch_rate', 'tier_bonus', 'marks_deduction', 'marks_reduce')", name="kind"),
        CheckConstraint("threshold >= 0", name="threshold"),
        CheckConstraint("amount >= 0", name="amount"),
        CheckConstraint("(kind = 'marks_reduce') = (amount IS NULL)", name="amount_kind"),
        SCHEMA,
    )

    scheme_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payroll.schemes.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    threshold: Mapped[Decimal] = mapped_column(Numeric(12, 3), primary_key=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))


class SchemeChangeRequest(Base):
    """A driver asks from the app to move to another of his platform's schemes from the next month."""

    __tablename__ = "scheme_change_requests"
    __table_args__ = (
        CheckConstraint("extract(day FROM effective_month) = 1", name="month"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status"),
        CheckConstraint("requested_scheme_id IS DISTINCT FROM current_scheme_id", name="change"),
        CheckConstraint("(status IN ('approved', 'rejected')) = (decided_at IS NOT NULL)", name="decided"),
        Index(
            "scheme_change_requests_employee_id_idx",
            "employee_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("scheme_change_requests_status_idx", "status", "created_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    current_scheme_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.schemes.id"))
    requested_scheme_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.schemes.id"))
    effective_month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    driver_note: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    submitted_by_device: Mapped[int | None] = mapped_column(BigInteger)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class DriverScheme(Base):
    """Which scheme a driver is on, month by month (valid_to exclusive, none: still on it). The database refuses two
    rows for the same driver and month (an exclusion constraint in the migration)."""

    __tablename__ = "driver_schemes"
    __table_args__ = (
        CheckConstraint(
            "extract(day FROM valid_from) = 1 AND "
            "(valid_to IS NULL OR (extract(day FROM valid_to) = 1 AND valid_to > valid_from))",
            name="month",
        ),
        CheckConstraint("source IN ('office', 'registration', 'request', 'import')", name="source"),
        Index("driver_schemes_scheme_id_idx", "scheme_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    scheme_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.schemes.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text)
    request_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.scheme_change_requests.id"))
    set_by: Mapped[int | None] = mapped_column(BigInteger)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Uncollected(Base):
    """Decision D: what a month's pay could not cover of its penalties (the net stops at zero), recorded when the run
    is approved, for review. Carried to a later month (a manual deduction) or dropped, each with a note; never carried
    by itself."""

    __tablename__ = "uncollected"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", "round", name="uncollected_run_id_key"),
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("status IN ('review', 'carried', 'dropped')", name="status"),
        CheckConstraint("(status = 'review') = (decided_at IS NULL)", name="decided"),
        CheckConstraint("status = 'review' OR note IS NOT NULL", name="note"),
        CheckConstraint("(status = 'carried') = (deduction_id IS NOT NULL)", name="carried"),
        Index("uncollected_month_idx", "month", "status"),
        Index("uncollected_employee_id_idx", "employee_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.runs.id"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    month: Mapped[date] = mapped_column(Date)
    round: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'review'"))
    note: Mapped[str | None] = mapped_column(Text)
    deduction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.deductions.id"))
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Objection(Base):
    """A driver's objection to his payslip (all of it, or one line), answered by the office. Never edits the run."""

    __tablename__ = "objections"
    __table_args__ = (
        CheckConstraint("extract(day FROM month) = 1", name="month"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason"),
        CheckConstraint("status IN ('open', 'in_review', 'accepted', 'rejected', 'closed')", name="status"),
        CheckConstraint("status NOT IN ('accepted', 'rejected') OR response IS NOT NULL", name="answered"),
        Index("objections_status_idx", "status", "created_at"),
        Index("objections_employee_id_idx", "employee_id", "created_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("payroll.runs.id"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    month: Mapped[date] = mapped_column(Date)
    item_code: Mapped[str | None] = mapped_column(Text)
    item_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(Text)
    attachment_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    response: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
    deduction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.deductions.id"))
    handled_by: Mapped[int | None] = mapped_column(BigInteger)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_ref: Mapped[uuid.UUID] = mapped_column(UUID, unique=True)
    submitted_by_device: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
