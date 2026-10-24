import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppRelease(Base):
    """One APK of the driver app, as uploaded; drivers see it once published."""

    __tablename__ = "app_releases"
    __table_args__ = (
        CheckConstraint("version_code > 0", name="version_code"),
        CheckConstraint("status IN ('draft', 'published')", name="status"),
        Index("app_releases_status_idx", "status", "version_code"),
        {"schema": "org"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, server_default=text("gen_random_uuid()"))
    version_code: Mapped[int] = mapped_column(Integer, unique=True)
    version_name: Mapped[str] = mapped_column(Text)
    package: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text, ForeignKey("files.files.sha256"))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    notes: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))  # {lang: text}
    required: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # older apps must update
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
