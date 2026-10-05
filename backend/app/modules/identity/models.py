import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    locale: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)  # a TOTP code can be used once
    is_superuser: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    all_companies: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
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
    name: Mapped[dict] = mapped_column(JSONB)
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    all_permissions: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
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


class UserCompany(Base):
    __tablename__ = "user_companies"
    __table_args__ = SCHEMA

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("identity.users.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.companies.id"), primary_key=True)


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


# ---------------------------------------------------------------- driver devices (M1)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("devices_employee_id_idx", "employee_id", unique=True, postgresql_where=text("revoked_at IS NULL")),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    device_uid: Mapped[str] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(Text)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    __table_args__ = (
        CheckConstraint("kind IN ('access', 'refresh')", name="kind"),
        Index("device_tokens_family_idx", "family"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("identity.devices.id"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    family: Mapped[uuid.UUID] = mapped_column(UUID)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (Index("otp_challenges_phone_idx", "phone", "created_at"), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(Text)
    employee_id: Mapped[int | None] = mapped_column(BigInteger)
    device_uid: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(Text)


class DeviceStatus(Base):
    __tablename__ = "device_status"
    __table_args__ = SCHEMA

    device_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("identity.devices.id"), primary_key=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    location_permission: Mapped[str | None] = mapped_column(Text)
    gps_enabled: Mapped[bool | None] = mapped_column(Boolean)
    battery_optimization_ignored: Mapped[bool | None] = mapped_column(Boolean)
    tracking_service_running: Mapped[bool | None] = mapped_column(Boolean)
    battery_level: Mapped[int | None] = mapped_column(SmallInteger)
    queue_size: Mapped[int | None] = mapped_column(Integer)
    last_upload_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    app_version: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))


class ActivationLink(Base):
    """One-time link sent to the driver's registered number; its token is stored only as a hash."""

    __tablename__ = "activation_links"
    __table_args__ = (
        CheckConstraint("channel IN ('whatsapp', 'manual')", name="channel"),
        Index("activation_links_employee_id_idx", "employee_id", "created_at"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    channel: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_device_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.devices.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LinkQueueItem(Base):
    """An activation link waiting to be sent over WhatsApp (bulk sending, spaced out)."""

    __tablename__ = "link_queue"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'failed', 'cancelled')", name="status"),
        Index("link_queue_employee_id_idx", "employee_id", unique=True, postgresql_where=text("status = 'queued'")),
        Index("link_queue_status_idx", "status", "id"),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    onboarding: Mapped[bool] = mapped_column(Boolean)
    requested_by: Mapped[int] = mapped_column(BigInteger)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class DriverClaim(Base):
    """A one-time sign-in by civil ID and an initial password, for a driver the office has no phone for."""

    __tablename__ = "driver_claims"
    __table_args__ = (
        Index(
            "driver_claims_session_hash_idx",
            "session_hash",
            unique=True,
            postgresql_where=text("session_hash IS NOT NULL"),
        ),
        SCHEMA,
    )

    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    failures: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_hash: Mapped[str | None] = mapped_column(Text)
    session_device_uid: Mapped[str | None] = mapped_column(Text)
    session_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone: Mapped[str | None] = mapped_column(Text)
    otp_hash: Mapped[str | None] = mapped_column(Text)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_sent: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    otp_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_phone: Mapped[str | None] = mapped_column(Text)
    used_device_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("identity.devices.id"))


class ClaimAttempt(Base):
    __tablename__ = "claim_attempts"
    __table_args__ = (Index("claim_attempts_ip_idx", "ip", "at"), SCHEMA)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ip: Mapped[str | None] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
