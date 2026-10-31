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


class AppRelease(Base):
    """One APK of the driver app, as uploaded; drivers see it once published."""

    __tablename__ = "app_releases"
    __table_args__ = (
        CheckConstraint("version_code > 0", name="version_code"),
        CheckConstraint("status IN ('draft', 'published')", name="status"),
        CheckConstraint("origin IN ('upload', 'github')", name="origin"),
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
    created_by: Mapped[int | None] = mapped_column(BigInteger)  # None: imported by the hourly job
    origin: Mapped[str] = mapped_column(Text, server_default=text("'upload'"))  # upload | github
    github_tag: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppUpdateState(Base):
    """One row: what was last written to Firebase Remote Config, and last read from GitHub."""

    __tablename__ = "app_update_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="id"),
        CheckConstraint("remote_state IN ('never', 'published', 'failed', 'not_configured')", name="remote_state"),
        CheckConstraint("github_state IN ('never', 'imported', 'up_to_date', 'failed')", name="github_state"),
        {"schema": "org"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=text("1"))
    remote_state: Mapped[str] = mapped_column(Text, server_default=text("'never'"))
    remote_error: Mapped[str | None] = mapped_column(Text)
    remote_values: Mapped[dict | None] = mapped_column(JSONB)
    remote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_state: Mapped[str] = mapped_column(Text, server_default=text("'never'"))
    github_error: Mapped[str | None] = mapped_column(Text)
    github_release: Mapped[str | None] = mapped_column(Text)
    github_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
