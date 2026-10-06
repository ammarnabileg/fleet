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
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "people"}


class EmploymentStatus(Base):
    __tablename__ = "employment_statuses"
    __table_args__ = (CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,30}$'", name="code"), SCHEMA)

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[dict] = mapped_column(JSONB)
    is_working: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_terminal: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("100"))


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("civil_id ~ '^[0-9]{12}$'", name="civil_id"),
        CheckConstraint("phone ~ '^\\+[1-9][0-9]{7,14}$'", name="phone"),
        CheckConstraint("basic_salary >= 0", name="basic_salary"),
        CheckConstraint("app_access IN ('none', 'active', 'suspended', 'disabled')", name="app_access"),
        CheckConstraint("payment_method IN ('bank', 'cash')", name="payment_method"),
        CheckConstraint("platform_driver_id IS NULL OR platform_id IS NOT NULL", name="platform_driver"),
        Index(
            "employees_platform_driver_id_idx",
            "platform_id",
            func.lower(text("platform_driver_id")),
            unique=True,
            postgresql_where=text("platform_driver_id IS NOT NULL"),
        ),
        Index("employees_phone_idx", "phone", unique=True, postgresql_where=text("phone IS NOT NULL")),
        Index("employees_company_id_idx", "company_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_number: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[dict] = mapped_column(JSONB)
    civil_id: Mapped[str | None] = mapped_column(Text, unique=True)
    nationality: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    department: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    is_driver: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    phone: Mapped[str | None] = mapped_column(Text)
    hire_date: Mapped[date | None] = mapped_column(Date)
    basic_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    iban: Mapped[str | None] = mapped_column(Text)
    bank_name: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[str | None] = mapped_column(Text)  # bank | cash
    platform_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.platforms.id"))
    platform_driver_id: Mapped[str | None] = mapped_column(Text)  # the driver's ID on his platform
    status_code: Mapped[str] = mapped_column(Text, ForeignKey("people.employment_statuses.code"))
    app_access: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class StatusHistory(Base):
    __tablename__ = "status_history"
    __table_args__ = (Index("status_history_employee_id_idx", "employee_id", "id"), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    status_code: Mapped[str] = mapped_column(Text, ForeignKey("people.employment_statuses.code"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    changed_by: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)


class ExternalRef(Base):
    __tablename__ = "external_refs"
    __table_args__ = (UniqueConstraint("system", "employee_id", name="external_refs_system_employee_key"), SCHEMA)

    system: Mapped[str] = mapped_column(Text, primary_key=True)
    external_id: Mapped[str] = mapped_column(Text, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
