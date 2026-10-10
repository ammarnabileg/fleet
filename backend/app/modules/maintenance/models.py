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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "maintenance"}
KINDS = ("periodic", "mechanical", "electrical", "tyres", "battery", "ac", "bodywork", "other")
STATUSES = (
    "requested",
    "approved",
    "rejected",
    "referred",
    "received",
    "inspection",
    "quote_pending",
    "in_repair",
    "waiting_parts",
    "completed",
    "ready",
    "picked_up",
    "closed",
    "cancelled",
)
AT_CENTER = ("referred", "received", "inspection", "quote_pending", "in_repair", "waiting_parts", "completed", "ready")
NUMBER_SEQ = Sequence("request_number_seq", schema="maintenance")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Center(Base):
    __tablename__ = "centers"
    __table_args__ = (Index("centers_name_idx", func.lower(text("name")), unique=True), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text)
    specialty: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class CenterUser(Base):
    """A portal account: an identity user who works for one center and sees only what was referred to it."""

    __tablename__ = "center_users"
    __table_args__ = (Index("center_users_center_id_idx", "center_id"), SCHEMA)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("identity.users.id", ondelete="CASCADE"), primary_key=True
    )
    center_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance.centers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(KINDS)})", name="kind"),
        CheckConstraint(f"status IN ({_in(STATUSES)})", name="status"),
        CheckConstraint("odometer_km >= 0", name="odometer_km"),
        CheckConstraint("created_by_user IS NOT NULL OR created_by_device IS NOT NULL", name="creator"),
        CheckConstraint("status <> 'rejected' OR decision_note IS NOT NULL", name="rejected"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        CheckConstraint(
            "center_id IS NOT NULL OR status IN ('requested', 'approved', 'rejected', 'cancelled')", name="center"
        ),
        Index(
            "requests_one_at_center_idx",
            "vehicle_id",
            unique=True,
            postgresql_where=text(f"status IN ({_in(AT_CENTER)})"),
        ),
        Index("requests_status_idx", "status", "created_at"),
        Index("requests_vehicle_id_idx", "vehicle_id", "created_at"),
        Index("requests_center_id_idx", "center_id", "status"),
        Index("requests_driver_id_idx", "driver_id", "created_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(Integer, NUMBER_SEQ, unique=True, server_default=NUMBER_SEQ.next_value())
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    kind: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    emergency: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # sent by the driver straight to the center he picked: no quote needed, the invoice before "ready", his pickup
    direct: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'requested'"))
    client_ref: Mapped[uuid.UUID | None] = mapped_column(UUID, unique=True)
    created_by_user: Mapped[int | None] = mapped_column(BigInteger)
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    emergency_reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    emergency_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    center_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("maintenance.centers.id"))
    referred_by: Mapped[int | None] = mapped_column(BigInteger)
    referred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by: Mapped[int | None] = mapped_column(BigInteger)
    received_km: Mapped[int | None] = mapped_column(Integer)
    condition_note: Mapped[str | None] = mapped_column(Text)
    repair_details: Mapped[str | None] = mapped_column(Text)
    final_km: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    picked_up_by: Mapped[int | None] = mapped_column(BigInteger)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class RequestPhoto(Base):
    __tablename__ = "request_photos"
    __table_args__ = (CheckConstraint("stage IN ('request', 'reception', 'repair')", name="stage"), SCHEMA)

    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance.requests.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"), primary_key=True)


class RequestEvent(Base):
    __tablename__ = "request_events"
    __table_args__ = (Index("request_events_request_id_idx", "request_id", "at"), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance.requests.id"))
    status: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    by_user: Mapped[int | None] = mapped_column(BigInteger)
    by_device: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
        CheckConstraint("status <> 'rejected' OR reason IS NOT NULL", name="rejected"),
        Index("quotes_one_pending_idx", "request_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("quotes_request_id_idx", "request_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance.requests.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    items: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'"))
    notes: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    auto_approved: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("total > 0", name="total"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
        CheckConstraint("payment_status IN ('unpaid', 'paid')", name="payment_status"),
        CheckConstraint("status <> 'rejected' OR reason IS NOT NULL", name="rejected"),
        CheckConstraint("(payment_status = 'paid') = (paid_at IS NOT NULL)", name="paid"),
        CheckConstraint("payment_status = 'unpaid' OR status = 'approved'", name="paid_approved"),
        Index("invoices_center_id_idx", "center_id", func.lower(text("number"))),
        Index("invoices_status_idx", "status", "created_at"),
        Index("invoices_request_id_idx", "request_id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    center_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance.centers.id"))
    request_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("maintenance.requests.id"))
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    number: Mapped[str] = mapped_column(Text)
    invoice_date: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    file_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"))
    notes: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    payment_status: Mapped[str] = mapped_column(Text, server_default=text("'unpaid'"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[int | None] = mapped_column(BigInteger)
    payment_ref: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("kind IN ('part', 'labour', 'other')", name="kind"),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("unit_price >= 0", name="unit_price"),
        SCHEMA,
    )

    invoice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance.invoices.id"), primary_key=True)
    line: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 3))
