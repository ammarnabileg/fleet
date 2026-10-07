import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = {"schema": "documents"}


class DocumentType(Base):
    __tablename__ = "document_types"
    __table_args__ = (CheckConstraint("applies_to IN ('employee', 'vehicle', 'company')", name="applies_to"), SCHEMA)

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[dict] = mapped_column(JSONB)
    applies_to: Mapped[str] = mapped_column(Text)
    requires_expiry: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("100"))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("owner_type IN ('employee', 'vehicle', 'company')", name="owner_type"),
        Index(
            "documents_current_idx",
            "type_code",
            "owner_type",
            "owner_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("documents_expiry_date_idx", "expiry_date", postgresql_where=text("is_current")),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    type_code: Mapped[str] = mapped_column(Text, ForeignKey("documents.document_types.code"))
    owner_type: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(BigInteger)
    company_id: Mapped[int] = mapped_column(BigInteger)
    number: Mapped[str | None] = mapped_column(Text)
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    file_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    file_back_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("files.files.sha256"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Renewal(Base):
    """A renewed document the driver sends from the app (BRD FR-APP-05): it becomes his current document once the
    office has checked it against the photo."""

    __tablename__ = "renewals"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
        Index(
            "renewals_one_pending_idx",
            "employee_id",
            "type_code",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        SCHEMA,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("people.employees.id"))
    company_id: Mapped[int] = mapped_column(BigInteger)
    type_code: Mapped[str] = mapped_column(Text, ForeignKey("documents.document_types.code"))
    number: Mapped[str | None] = mapped_column(Text)
    expiry_date: Mapped[date] = mapped_column(Date)
    file_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_device: Mapped[int | None] = mapped_column(BigInteger)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("documents.documents.id"))
