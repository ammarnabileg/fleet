from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StoredFile(Base):
    """Immutable, named by its sha256."""

    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        CheckConstraint("size_bytes > 0", name="size_bytes"),
        CheckConstraint("content_type IN ('image/jpeg', 'image/png', 'application/pdf')", name="content_type"),
        CheckConstraint("source IN ('camera', 'upload')", name="source"),
        CheckConstraint("storage IN ('local', 'r2')", name="storage"),
        Index("files_storage_idx", "storage"),
        {"schema": "files"},
    )

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    uploaded_by_user: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_by_device: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    storage: Mapped[str] = mapped_column(Text, server_default=text("'local'"))  # where the bytes are
