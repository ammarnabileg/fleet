import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "accidents"}
NUMBER_SEQ = Sequence("accident_number_seq", schema="accidents")
LIABILITIES = ("none", "driver", "shared")


class Accident(Base):
    """One accident: the report, the police report, the center's damage estimate and its approval, the liability
    outcome with the deduction it created, and the repair request that fixes the vehicle."""

    __tablename__ = "accidents"
    __table_args__ = (
        CheckConstraint("estimate_status IN ('none', 'pending', 'approved', 'rejected')", name="estimate_status"),
        CheckConstraint("estimate_total > 0", name="estimate_total"),
        CheckConstraint("liability IN ('none', 'driver', 'shared')", name="liability"),
        CheckConstraint("liability_percent > 0 AND liability_percent <= 100", name="liability_percent"),
        CheckConstraint("status IN ('open', 'closed', 'cancelled')", name="status"),
        CheckConstraint("reported_by_user IS NOT NULL OR reported_by_device IS NOT NULL", name="reporter"),
        CheckConstraint("liability IS NULL OR police_report_sha256 IS NOT NULL", name="outcome"),
        CheckConstraint("estimate_status = 'none' OR center_id IS NOT NULL", name="estimate"),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancelled"),
        Index("accidents_status_idx", "status", "occurred_at"),
        Index("accidents_vehicle_id_idx", "vehicle_id", "occurred_at"),
        Index("accidents_driver_id_idx", "driver_id", "occurred_at"),
        Index("accidents_center_id_idx", "center_id", "estimate_status"),
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
    lat: Mapped[float | None] = mapped_column(Double)
    lng: Mapped[float | None] = mapped_column(Double)
    location_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    injuries: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    injuries_note: Mapped[str | None] = mapped_column(Text)
    other_party: Mapped[str | None] = mapped_column(Text)
    client_ref: Mapped[uuid.UUID | None] = mapped_column(UUID, unique=True)
    reported_by_user: Mapped[int | None] = mapped_column(BigInteger)
    reported_by_device: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    police_report_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    police_report_no: Mapped[str | None] = mapped_column(Text)
    police_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    center_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("maintenance.centers.id"))
    referred_by: Mapped[int | None] = mapped_column(BigInteger)
    referred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimate_status: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    estimate_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    estimate_items: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'"))
    estimate_notes: Mapped[str | None] = mapped_column(Text)
    estimate_file_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    estimated_by: Mapped[int | None] = mapped_column(BigInteger)
    estimated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimate_decided_by: Mapped[int | None] = mapped_column(BigInteger)
    estimate_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimate_reason: Mapped[str | None] = mapped_column(Text)
    liability: Mapped[str | None] = mapped_column(Text)
    liability_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    outcome_note: Mapped[str | None] = mapped_column(Text)
    outcome_by: Mapped[int | None] = mapped_column(BigInteger)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deduction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payroll.deductions.id"))
    repair_request_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("maintenance.requests.id"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class AccidentPhoto(Base):
    __tablename__ = "accident_photos"
    __table_args__ = (SCHEMA,)

    accident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accidents.accidents.id"), primary_key=True)
    file_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"), primary_key=True)


class AccidentEvent(Base):
    """The timeline: what happened, when and by whom. A note starting with ":" is a code the screens translate."""

    __tablename__ = "accident_events"
    __table_args__ = (Index("accident_events_accident_id_idx", "accident_id", "at"), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    accident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accidents.accidents.id"))
    kind: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    by_user: Mapped[int | None] = mapped_column(BigInteger)
    by_device: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)
