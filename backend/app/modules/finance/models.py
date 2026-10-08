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
    Sequence,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "finance"}
EXPENSE_SEQ = Sequence("expense_number_seq", schema="finance")
ENTRY_SEQ = Sequence("entry_number_seq", schema="finance")
ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")
PAYMENT_METHODS = ("treasury", "bank", "payable")
SOURCE_KINDS = (
    "cash_journal",
    "expense",
    "expense_payment",
    "maintenance_invoice",
    "invoice_payment",
    "payroll_run",
    "payroll_payment",
    "deduction",
    "fine_payment",
    "reversal",
    "manual",
    "opening",
)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(r"code ~ '^[0-9A-Za-z][0-9A-Za-z.\-]{0,19}$'", name="code"),
        CheckConstraint("type IN ('asset', 'liability', 'equity', 'income', 'expense')", name="type"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[dict] = mapped_column(JSONB)
    type: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class AccountRole(Base):
    """Which account a posting uses: "treasury", "salaries_payable"... (app.modules.finance.posting.ROLES)."""

    __tablename__ = "account_roles"
    __table_args__ = (SCHEMA,)

    role: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finance.accounts.id"))


class ExpenseType(Base):
    __tablename__ = "expense_types"
    __table_args__ = (CheckConstraint("code ~ '^[a-z][a-z0-9_]{1,30}$'", name="code"), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[dict] = mapped_column(JSONB)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finance.accounts.id"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("100"))


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("payment_method IN ('treasury', 'bank', 'payable')", name="payment_method"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status"),
        CheckConstraint("paid_from IN ('treasury', 'bank')", name="paid_from"),
        CheckConstraint("status <> 'rejected' OR decision_note IS NOT NULL", name="rejected"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        CheckConstraint("status NOT IN ('approved', 'rejected') OR decided_at IS NOT NULL", name="decided"),
        CheckConstraint("status <> 'pending' OR decided_at IS NULL", name="undecided"),
        CheckConstraint("(paid_at IS NULL) = (paid_from IS NULL)", name="paid"),
        CheckConstraint("paid_at IS NULL OR (payment_method = 'payable' AND status = 'approved')", name="paid_payable"),
        Index("expenses_status_idx", "status", "expense_date"),
        Index("expenses_vehicle_id_idx", "vehicle_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(Integer, EXPENSE_SEQ, unique=True, server_default=EXPENSE_SEQ.next_value())
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finance.expense_types.id"))
    expense_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    payment_method: Mapped[str] = mapped_column(Text)
    supplier: Mapped[str | None] = mapped_column(Text)
    reference_no: Mapped[str | None] = mapped_column(Text)
    vehicle_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    employee_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    center_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("maintenance.centers.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    paid_from: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[int | None] = mapped_column(BigInteger)
    payment_ref: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class ExpenseFile(Base):
    __tablename__ = "expense_files"
    __table_args__ = (SCHEMA,)

    expense_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finance.expenses.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger)


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('cash_journal', 'expense', 'expense_payment', 'maintenance_invoice', 'invoice_payment', "
            "'payroll_run', 'payroll_payment', 'deduction', 'fine_payment', 'reversal', 'manual', 'opening')",
            name="source_kind",
        ),
        CheckConstraint("status IN ('draft', 'approved')", name="status"),
        CheckConstraint("(source_kind = 'reversal') = (reverses_id IS NOT NULL)", name="reversal"),
        CheckConstraint("source_kind IN ('reversal', 'manual', 'opening') OR source_id IS NOT NULL", name="source"),
        CheckConstraint("source_kind <> 'reversal' OR reason IS NOT NULL", name="reason"),
        CheckConstraint("(status = 'approved') = (approved_at IS NOT NULL)", name="approved"),
        CheckConstraint("reversed_by_id IS NULL OR status = 'approved'", name="reversed"),
        Index(
            "entries_one_per_source",
            "source_kind",
            "source_id",
            unique=True,
            postgresql_where=text("source_kind <> 'reversal' AND reversed_by_id IS NULL"),
        ),
        Index("entries_one_reversal", "reverses_id", unique=True, postgresql_where=text("reverses_id IS NOT NULL")),
        Index(
            "entries_old_ref",
            "source_ref",
            unique=True,
            postgresql_where=text("source_kind = 'manual' AND source_ref LIKE 'OLD-%' AND reversed_by_id IS NULL"),
        ),
        Index("entries_entry_date_idx", "entry_date", "id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(Integer, ENTRY_SEQ, unique=True, server_default=ENTRY_SEQ.next_value())
    entry_date: Mapped[date] = mapped_column(Date)
    source_kind: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    source_ref: Mapped[str] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    reverses_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("finance.entries.id"))
    reversed_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("finance.entries.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[int | None] = mapped_column(BigInteger)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntryLine(Base):
    __tablename__ = "entry_lines"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0) <> (credit = 0)", name="amount"),
        Index("entry_lines_account_id_idx", "account_id"),
        Index("entry_lines_employee_id_idx", "employee_id", postgresql_where=text("employee_id IS NOT NULL")),
        SCHEMA,
    )

    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("finance.entries.id", ondelete="CASCADE"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("finance.accounts.id"))
    debit: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    memo: Mapped[str | None] = mapped_column(Text)
    employee_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))  # the party
