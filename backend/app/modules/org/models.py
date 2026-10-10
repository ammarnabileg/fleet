import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "org"}


class Company(Base):
    """A legal entity: employees are on its papers and vehicles are registered to it."""

    __tablename__ = "companies"
    __table_args__ = SCHEMA

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    name: Mapped[dict] = mapped_column(JSONB)
    trade_name: Mapped[dict | None] = mapped_column(JSONB)
    cr_number: Mapped[str | None] = mapped_column(Text, unique=True)
    license_number: Mapped[str | None] = mapped_column(Text)
    license_expiry: Mapped[date | None] = mapped_column(Date)
    pam_file_number: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Branch(Base):
    """An operational location. It does not limit what anyone can see."""

    __tablename__ = "branches"
    __table_args__ = (
        Index("branches_is_default_idx", "is_default", unique=True, postgresql_where=text("is_default")),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    name: Mapped[dict] = mapped_column(JSONB)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = SCHEMA

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
