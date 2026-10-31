from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

sql_text = text

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
    strings_version: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))


class Translation(Base):
    """A text edited from the dashboard, or a shipped text marked as reviewed (see migration 0063)."""

    __tablename__ = "translations"
    __table_args__ = (
        CheckConstraint("scope IN ('app', 'server', 'status_templates')", name="scope"),
        CheckConstraint("status IN ('machine', 'needs_review', 'reviewed')", name="status"),
        Index("translations_lang_idx", "lang", "scope"),
        SCHEMA,
    )

    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    lang: Mapped[str] = mapped_column(Text, ForeignKey("i18n.languages.code"), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=sql_text("'needs_review'"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class State(Base):
    __tablename__ = "state"
    __table_args__ = (CheckConstraint("singleton", name="singleton"), SCHEMA)

    singleton: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default=text("true"))
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    drafts_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bundle(Base):
    """A published version of a language's texts (immutable)."""

    __tablename__ = "bundles"
    __table_args__ = (CheckConstraint("version > 0", name="version"), SCHEMA)

    lang: Mapped[str] = mapped_column(Text, ForeignKey("i18n.languages.code"), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    overrides: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
