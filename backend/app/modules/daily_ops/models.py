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
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Report(Base):
    """A driver's day: orders, cash collected, the screenshot of the platform's daily summary."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("orders_count >= 0", name="orders_count"),
        CheckConstraint("cash_amount >= 0", name="cash_amount"),
        CheckConstraint("status IN ('submitted', 'approved', 'rejected')", name="status"),
        Index(
            "reports_one_per_day_idx",
            "employee_id",
            "business_date",
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
