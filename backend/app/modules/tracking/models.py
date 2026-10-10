from datetime import datetime

from sqlalchemy import REAL, BigInteger, CheckConstraint, DateTime, Double, Integer, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "tracking"}


class Position(Base):
    """Partitioned by month (Kuwait time); partitions are managed by tracking.ensure_month_partition()."""

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="lng"),
        {"schema": "tracking", "postgresql_partition_by": "RANGE (recorded_at)"},
    )

    vehicle_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    custody_id: Mapped[int] = mapped_column(BigInteger)
    driver_id: Mapped[int] = mapped_column(BigInteger)
    device_id: Mapped[int] = mapped_column(BigInteger)
    device_seq: Mapped[int] = mapped_column(BigInteger)
    device_offset_s: Mapped[int] = mapped_column(Integer, server_default="0")
    lat: Mapped[float] = mapped_column(Double)
    lng: Mapped[float] = mapped_column(Double)
    accuracy_m: Mapped[float | None] = mapped_column(REAL)
    speed_kmh: Mapped[float | None] = mapped_column(REAL)
    heading: Mapped[int | None] = mapped_column(SmallInteger)


class LastPosition(Base):
    __tablename__ = "last_positions"
    __table_args__ = SCHEMA

    vehicle_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    custody_id: Mapped[int] = mapped_column(BigInteger)
    driver_id: Mapped[int] = mapped_column(BigInteger)
    lat: Mapped[float] = mapped_column(Double)
    lng: Mapped[float] = mapped_column(Double)
    speed_kmh: Mapped[float | None] = mapped_column(REAL)
    heading: Mapped[int | None] = mapped_column(SmallInteger)
    signal_lost_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MockEvent(Base):
    __tablename__ = "mock_events"
    __table_args__ = SCHEMA

    device_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    driver_id: Mapped[int] = mapped_column(BigInteger)
    custody_id: Mapped[int | None] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RejectedPoint(Base):
    __tablename__ = "rejected_points"
    __table_args__ = SCHEMA

    device_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reason: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
