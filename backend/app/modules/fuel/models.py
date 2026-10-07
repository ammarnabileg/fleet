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
    Sequence,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "fuel"}
FUEL_TYPES = ("premium_91", "super_95", "ultra_98", "diesel")
NUMBER_SEQ = Sequence("fill_number_seq", schema="fuel")


class Price(Base):
    """The official price per litre of a fuel from a date (BRD FR-FUL-05)."""

    __tablename__ = "prices"
    __table_args__ = (
        CheckConstraint("fuel_type IN ('premium_91', 'super_95', 'ultra_98', 'diesel')", name="fuel_type"),
        CheckConstraint("price > 0", name="price"),
        UniqueConstraint("fuel_type", "effective_from", name="prices_fuel_type_effective_from_key"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fuel_type: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    effective_from: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelSpec(Base):
    """What a make and model takes, holds and burns (BRD FR-FUL-02, FR-FUL-04)."""

    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint("tank_litres > 0", name="tank_litres"),
        CheckConstraint(
            "cardinality(fuel_types) > 0 AND fuel_types <@ ARRAY['premium_91', 'super_95', 'ultra_98', 'diesel']",
            name="fuel_types",
        ),
        CheckConstraint("litres_per_100km > 0", name="litres_per_100km"),
        Index("models_make_model_idx", func.lower(text("make")), func.lower(text("model")), unique=True),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    make: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    tank_litres: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    fuel_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    litres_per_100km: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    updated_by: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Fill(Base):
    """A fill-up with its invoice and odometer, the checks it failed, and who decided it."""

    __tablename__ = "fills"
    __table_args__ = (
        CheckConstraint("litres > 0", name="litres"),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("fuel_type IN ('premium_91', 'super_95', 'ultra_98', 'diesel')", name="fuel_type"),
        CheckConstraint("odometer_km >= 0", name="odometer_km"),
        CheckConstraint("source IN ('app', 'office')", name="source"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
        CheckConstraint(
            "status <> 'approved' OR cardinality(flags) = 0 OR (decided_by IS NOT NULL AND decision_note IS NOT NULL)",
            name="flagged",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (decided_by IS NOT NULL AND decision_note IS NOT NULL)", name="rejected"
        ),
        CheckConstraint("(status = 'pending') = (decided_at IS NULL)", name="decided"),
        CheckConstraint("(created_by_user IS NULL) <> (created_by_device IS NULL)", name="author"),
        Index("fills_invoice_sha256_idx", "invoice_sha256", unique=True, postgresql_where=text("status <> 'rejected'")),
        Index("fills_vehicle_id_idx", "vehicle_id", "filled_at"),
        Index("fills_status_idx", "status", "filled_at"),
        Index("fills_driver_id_idx", "driver_id", "filled_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(Integer, NUMBER_SEQ, unique=True, server_default=NUMBER_SEQ.next_value())
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    custody_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("fleet.custodies.id"))
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date)
    litres: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    fuel_type: Mapped[str] = mapped_column(Text)
    station: Mapped[str | None] = mapped_column(Text)
    odometer_km: Mapped[int] = mapped_column(Integer)
    invoice_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"))
    odometer_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    source: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    km_since: Mapped[int | None] = mapped_column(Integer)
    litres_per_100km: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    expense_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("finance.expenses.id"))
    created_by_user: Mapped[int | None] = mapped_column(BigInteger)
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
