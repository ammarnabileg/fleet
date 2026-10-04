import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "identity"}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("users_username_lower_key", func.lower(text("username")), unique=True), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)  # a TOTP code can be used once
    is_superuser: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    all_branches: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    failed_logins: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = SCHEMA

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name_ar: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = SCHEMA

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("identity.roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(Text, primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = SCHEMA

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("identity.users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("identity.roles.id", ondelete="CASCADE"), primary_key=True
    )


class UserBranch(Base):
    __tablename__ = "user_branches"
    __table_args__ = SCHEMA

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("identity.users.id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.branches.id"), primary_key=True)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("sessions_user_id_idx", "user_id", postgresql_where=text("revoked_at IS NULL")), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("identity.users.id", ondelete="CASCADE"))
    mfa_passed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    csrf_token: Mapped[str] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
