import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "fleet"}
STATUSES = ("available", "assigned", "maintenance", "accident", "inactive")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("year BETWEEN 1980 AND 2100", name="year"),
        CheckConstraint("status IN ('available', 'assigned', 'maintenance', 'accident', 'inactive')", name="status"),
        Index("vehicles_company_id_idx", "company_id"),
        Index(
            "vehicles_plate_number_idx",
            func.upper(func.regexp_replace(text("plate_number"), r"\s", "", "g")),
            unique=True,
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    plate_number: Mapped[str] = mapped_column(Text)  # unique ignoring spaces and case
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    color: Mapped[str | None] = mapped_column(Text)
    vin: Mapped[str | None] = mapped_column(Text, unique=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.branches.id"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'available'"))
    last_odometer_km: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Custody(Base):
    """Non-overlapping per vehicle and per driver: two exclusion constraints in the migration."""

    __tablename__ = "custodies"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="period"),
        CheckConstraint("kind <> 'emergency' OR reason IS NOT NULL", name="reason"),
        CheckConstraint("kind IN ('normal', 'emergency')", name="kind"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    driver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(Text, server_default=text("'normal'"))
    reason: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    handed_over_by: Mapped[int] = mapped_column(BigInteger)
    returned_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def covers(self, t: datetime) -> bool:
        return self.started_at <= t and (self.ended_at is None or t < self.ended_at)


class CustodyPhoto(Base):
    """Condition photos of the vehicle at handover and return."""

    __tablename__ = "custody_photos"
    __table_args__ = (
        CheckConstraint("stage IN ('handover', 'return')", name="stage"),
        CheckConstraint("position IN ('front', 'back', 'left', 'right', 'interior', 'other')", name="position"),
        SCHEMA,
    )

    custody_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.custodies.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"), primary_key=True)


class OdometerReading(Base):
    __tablename__ = "odometer_readings"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('handover', 'return', 'start_day', 'end_day', 'maintenance_in', 'maintenance_out')", name="kind"
        ),
        CheckConstraint("value_km >= 0", name="value_km"),
        CheckConstraint("corrected_km >= 0", name="corrected_km"),
        CheckConstraint("review_status IN ('ok', 'pending', 'reviewed')", name="review_status"),
        CheckConstraint("corrected_km IS NULL OR review_reason IS NOT NULL", name="correction"),
        Index("odometer_readings_vehicle_id_idx", "vehicle_id", "recorded_at"),
        Index(
            "odometer_readings_start_day_idx",
            "custody_id",
            "business_date",
            unique=True,
            postgresql_where=text("kind = 'start_day'"),
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    custody_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("fleet.custodies.id"))
    driver_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text)
    value_km: Mapped[int] = mapped_column(Integer)
    corrected_km: Mapped[int | None] = mapped_column(Integer)
    photo_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lat: Mapped[float | None] = mapped_column(Double)
    lng: Mapped[float | None] = mapped_column(Double)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    review_status: Mapped[str] = mapped_column(Text, server_default=text("'ok'"))
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_by_user: Mapped[int | None] = mapped_column(BigInteger)
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)

    @property
    def effective_km(self) -> int:
        return self.corrected_km if self.corrected_km is not None else self.value_km


class VehicleChangeRequest(Base):
    """The driver asks from the app for another vehicle, with his reason (BRD FR-ASG-04); the supervisor changes it
    (the return closes the request) or refuses with a note."""

    __tablename__ = "vehicle_change_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'rejected')", name="status"),
        Index(
            "vehicle_change_requests_one_pending_idx",
            "custody_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    custody_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.custodies.id"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fleet.vehicles.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
