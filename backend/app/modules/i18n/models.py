from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "i18n"}


class Language(Base):
    __tablename__ = "languages"
    __table_args__ = (
        CheckConstraint("code ~ '^[a-z]{2,3}(-[A-Z]{2})?$'", name="code"),
        CheckConstraint("direction IN ('rtl', 'ltr')", name="direction"),
        CheckConstraint("NOT (is_default AND NOT is_active)", name="default_active"),
        CheckConstraint("fallback_code IS DISTINCT FROM code", name="fallback"),
        Index("languages_is_default_idx", "is_default", unique=True, postgresql_where=text("is_default")),
        SCHEMA,
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name_native: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    fallback_code: Mapped[str | None] = mapped_column(Text, ForeignKey("i18n.languages.code"))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("100"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Override(Base):
    __tablename__ = "overrides"
    __table_args__ = SCHEMA

    lang: Mapped[str] = mapped_column(Text, ForeignKey("i18n.languages.code"), primary_key=True)
    namespace: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class State(Base):
    __tablename__ = "state"
    __table_args__ = (CheckConstraint("singleton", name="singleton"), SCHEMA)

    singleton: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default=text("true"))
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
