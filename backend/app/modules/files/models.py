from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, Text, func
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
        {"schema": "files"},
    )

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    uploaded_by_user: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_by_device: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
