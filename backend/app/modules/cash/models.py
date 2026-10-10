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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "cash"}
ACCOUNT_KINDS = (
    "driver",
    "treasury",
    "bank",
    "cod_clearing",
    "adjustments",
    "payroll_recovery",
    "writeoff",
    "opening",
    "fuel",
    "disbursements",
    "petty",
)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('driver', 'treasury', 'bank', 'cod_clearing', 'adjustments', 'payroll_recovery', 'writeoff', "
            "'opening', 'fuel', 'disbursements', 'petty')",
            name="kind",
        ),
        CheckConstraint("(kind = 'driver') = (driver_id IS NOT NULL)", name="driver"),
        CheckConstraint("(kind = 'petty') = (employee_id IS NOT NULL)", name="petty"),
        UniqueConstraint(
            "kind",
            "driver_id",
            "branch_id",
            "employee_id",
            name="accounts_kind_key",
            postgresql_nulls_not_distinct=True,
        ),
        Index("accounts_one_petty", "employee_id", unique=True, postgresql_where=text("kind = 'petty'")),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    branch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    employee_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))  # petty's holder
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Journal(Base):
    """Append-only; enforced by triggers (see the migration)."""

    __tablename__ = "journals"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('collection', 'adjustment', 'deposit', 'bank_deposit', 'settlement', 'writeoff', 'reversal', "
            "'opening', 'fuel', 'disbursement', 'bank_withdrawal', 'count_diff', 'petty_fund', 'petty_return')",
            name="kind",
        ),
        CheckConstraint("status IN ('pending', 'posted', 'rejected')", name="status"),
        CheckConstraint(
            "kind NOT IN ('adjustment', 'reversal', 'writeoff', 'count_diff') OR reason IS NOT NULL", name="reason"
        ),
        CheckConstraint("(kind = 'reversal') = (reverses_id IS NOT NULL)", name="reversal"),
        CheckConstraint("created_by IS NOT NULL OR created_by_device IS NOT NULL", name="creator"),
        Index(
            "journals_one_per_source",
            "source_type",
            "source_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "status <> 'rejected' AND kind IN ('collection', 'deposit', 'settlement', 'opening', 'disbursement', "
                "'count_diff')"
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
    attachment_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))  # a deposit's receipt
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


class FuelClaim(Base):
    """Fuel a driver paid from the cash he holds, claimed from the app with the receipt's photo; the accountant
    approves it (posting a fuel journal when the company covers his fuel) or rejects it."""

    __tablename__ = "fuel_claims"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("odometer_km >= 0", name="odometer_km"),
        CheckConstraint("char_length(notes) <= 500", name="notes"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
        CheckConstraint("approved_amount > 0", name="approved_amount"),
        CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL) AND (status <> 'approved' OR approved_amount IS NOT NULL) "
            "AND (status <> 'rejected' OR decision_note IS NOT NULL)",
            name="decision",
        ),
        Index("fuel_claims_employee_id_idx", "employee_id", "paid_at"),
        Index("fuel_claims_status_idx", "status", "created_at"),
        Index("fuel_claims_created_at_idx", "created_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    client_ref: Mapped[uuid.UUID] = mapped_column(UUID, unique=True)  # the app's id: a resend is recognised
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    receipt_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    journal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cash.journals.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TreasuryClosing(Base):
    """A branch treasury's day counted and closed: the posted balance at the end of the day, the cash counted, and the
    difference (posted as a count_diff journal). Never changed except to be reopened (the last one only)."""

    __tablename__ = "treasury_closings"
    __table_args__ = (
        CheckConstraint("counted >= 0", name="counted"),
        CheckConstraint("difference = counted - book_balance", name="difference"),
        CheckConstraint("difference = 0 OR note IS NOT NULL", name="note"),
        CheckConstraint("(difference = 0) = (journal_id IS NULL)", name="journal"),
        CheckConstraint(
            "(reopened_at IS NULL) = (reopened_by IS NULL) AND (reopened_at IS NULL) = (reopen_reason IS NULL)",
            name="reopened",
        ),
        Index(
            "treasury_closings_active",
            "branch_id",
            "day",
            unique=True,
            postgresql_where=text("reopened_at IS NULL"),
        ),
        Index("treasury_closings_branch_id_idx", "branch_id", "day"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    day: Mapped[date] = mapped_column(Date)
    book_balance: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    counted: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    denominations: Mapped[dict | None] = mapped_column(JSONB)
    difference: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    note: Mapped[str | None] = mapped_column(Text)
    journal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cash.journals.id"))
    closed_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("identity.users.id"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reopened_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.users.id"))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(Text)
