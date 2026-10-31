import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "fines"}
NUMBER_SEQ = Sequence("fine_number_seq", schema="fines")
STATUSES = ("open", "charged", "company", "cancelled")


class Fine(Base):
    """A traffic fine on a vehicle, the driver who held it at that moment, and how it was settled."""

    __tablename__ = "fines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("status IN ('open', 'charged', 'company', 'cancelled')", name="status"),
        CheckConstraint("status <> 'charged' OR (deduction_id IS NOT NULL AND driver_id IS NOT NULL)", name="charged"),
        CheckConstraint("status <> 'company' OR decision_note IS NOT NULL", name="company"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        CheckConstraint("(paid_at IS NULL) = (paid_by IS NULL)", name="paid"),
        Index(
            "fines_reference_no_idx",
            func.lower(text("reference_no")),
            unique=True,
            postgresql_where=text("reference_no IS NOT NULL AND status <> 'cancelled'"),
        ),
        Index("fines_status_idx", "status", "occurred_at"),
        Index("fines_vehicle_id_idx", "vehicle_id", "occurred_at"),
        Index("fines_driver_id_idx", "driver_id", "occurred_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(Integer, NUMBER_SEQ, unique=True, server_default=NUMBER_SEQ.next_value())
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    custody_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("fleet.custodies.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reference_no: Mapped[str | None] = mapped_column(Text)
    violation: Mapped[str] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    file_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    deduction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.deductions.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[int | None] = mapped_column(BigInteger)
    payment_ref: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
