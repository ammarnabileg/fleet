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
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "cash"}
ACCOUNT_KINDS = ("driver", "treasury", "bank", "cod_clearing", "adjustments", "payroll_recovery", "writeoff", "opening")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('driver', 'treasury', 'bank', 'cod_clearing', 'adjustments', 'payroll_recovery', 'writeoff', "
            "'opening')",
            name="kind",
        ),
        CheckConstraint("(kind = 'driver') = (driver_id IS NOT NULL)", name="driver"),
        UniqueConstraint(
            "kind", "driver_id", "branch_id", name="accounts_kind_key", postgresql_nulls_not_distinct=True
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    branch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Journal(Base):
    """Append-only; enforced by triggers (see the migration)."""

    __tablename__ = "journals"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('collection', 'adjustment', 'deposit', 'bank_deposit', 'settlement', 'writeoff', 'reversal', "
            "'opening')",
            name="kind",
        ),
        CheckConstraint("status IN ('pending', 'posted', 'rejected')", name="status"),
        CheckConstraint("kind NOT IN ('adjustment', 'reversal', 'writeoff') OR reason IS NOT NULL", name="reason"),
        CheckConstraint("(kind = 'reversal') = (reverses_id IS NOT NULL)", name="reversal"),
        CheckConstraint("created_by IS NOT NULL OR created_by_device IS NOT NULL", name="creator"),
        Index(
            "journals_one_per_source",
            "source_type",
            "source_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "status <> 'rejected' AND kind IN ('collection', 'deposit', 'settlement', 'opening')"
            ),
        ),
        Index("journals_one_reversal", "reverses_id", unique=True, postgresql_where=text("kind = 'reversal'")),
        Index("journals_status_idx", "status", "created_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    kind: Mapped[str] = mapped_column(Text)
    business_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(BigInteger)
    reverses_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cash.journals.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="amount"),
        Index("journal_lines_account_id_idx", "account_id"),
        SCHEMA,
    )

    journal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cash.journals.id"), primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cash.accounts.id"), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        UniqueConstraint("branch_id", "receipt_no", name="receipts_branch_id_receipt_no_key"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    receipt_no: Mapped[int] = mapped_column(Integer)
    driver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    driver_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
