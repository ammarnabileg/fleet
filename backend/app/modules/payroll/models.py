import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "payroll"}
SOURCES = ("accident", "fine", "other")


class Deduction(Base):
    """What payroll deducts from an employee: a total in equal monthly installments from a start month."""

    __tablename__ = "deductions"
    __table_args__ = (
        CheckConstraint("source_type IN ('accident', 'fine', 'other')", name="source_type"),
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
