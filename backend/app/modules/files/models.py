from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StoredFile(Base):
    """Immutable, named by its sha256."""

    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        CheckConstraint("size_bytes > 0", name="size_bytes"),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'application/pdf', 'application/vnd.android.package-archive')",
            name="content_type",
        ),
        CheckConstraint("source IN ('camera', 'upload')", name="source"),
        CheckConstraint("on_disk OR in_r2", name="copy"),
        Index("files_to_r2_idx", "sha256", postgresql_where=text("on_disk AND NOT in_r2")),
        Index("files_to_disk_idx", "sha256", postgresql_where=text("in_r2 AND NOT on_disk")),
        {"schema": "files"},
    )

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    uploaded_by_user: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_by_device: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # where its copies are: the disk of the server that wrote or fetched it, the R2 bucket (shared by every server)
    on_disk: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    in_r2: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
