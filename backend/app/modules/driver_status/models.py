import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConfigVersion(Base):
    """Every publish of the status templates: the whole set as it was published. The newest is in force; going back
    to an earlier one publishes it again as a new version (restored_from)."""

    __tablename__ = "status_config_versions"
    __table_args__ = (CheckConstraint("version > 0", name="version"), {"schema": "notifications"})

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    templates: Mapped[dict] = mapped_column(JSONB)
    restored_from: Mapped[int | None] = mapped_column(Integer)
    changed: Mapped[str | None] = mapped_column(Text)  # the template code published, or none for a rollback
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContactRequest(Base):
    """A supervisor asks a driver to get in touch: the driver calls or acknowledges it in the app; the office closes
    it."""

    __tablename__ = "contact_requests"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'acknowledged', 'closed')", name="status"),
        CheckConstraint("char_length(message) BETWEEN 1 AND 300", name="message"),
        Index("contact_requests_employee_id_idx", "employee_id", "status"),
        {"schema": "notifications"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    created_by: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_client_ref: Mapped[uuid.UUID | None] = mapped_column(UUID)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(BigInteger)
