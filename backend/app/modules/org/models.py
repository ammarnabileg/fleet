import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "org"}


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = SCHEMA

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    name_ar: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = SCHEMA

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"))
    name_ar: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
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
