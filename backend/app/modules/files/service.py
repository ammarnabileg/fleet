"""Uploaded files: stored once, named by their sha256, never modified or deleted by the application.

The type is decided by the file's first bytes, never by its name or the declared content type. Files have no
download endpoint of their own: the module that references a file (a document, an odometer reading) serves it
after checking its own permission and company scope.
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.files.models import StoredFile

SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)
IMAGES = {"image/jpeg", "image/png"}


@dataclass(frozen=True)
class FileInfo:
    sha256: str
    size_bytes: int
    content_type: str
    source: str
    uploaded_by_user: int | None
    uploaded_by_device: int | None


def read_upload(file) -> bytes:
    """An uploaded file (FastAPI UploadFile), refused beyond the size limit without reading all of it."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, "file_too_large", max_mb=get_settings().max_upload_mb)
    return data


def sniff(data: bytes) -> str | None:
    return next((ctype for magic, ctype in SIGNATURES if data.startswith(magic)), None)


def path_of(sha256: str) -> Path:
    return Path(get_settings().files_dir) / sha256[:2] / sha256[2:4] / sha256


def store(
    db: Session,
    data: bytes,
    *,
    source: str,
    uploaded_by_user: int | None = None,
    uploaded_by_device: int | None = None,
    images_only: bool = False,
) -> FileInfo:
    """Writes the file (if new) and adds its row to the caller's transaction."""
    if not data:
        raise AppError(422, "file_empty")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise AppError(413, "file_too_large", max_mb=get_settings().max_upload_mb)
    ctype = sniff(data)
    if ctype is None or (images_only and ctype not in IMAGES):
        raise AppError(415, "file_type_not_allowed")
    sha = hashlib.sha256(data).hexdigest()
    target = path_of(sha)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)  # atomic: a reader never sees half a file
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    db.execute(
        insert(StoredFile)
        .values(
            sha256=sha,
            size_bytes=len(data),
            content_type=ctype,
            source=source,
            uploaded_by_user=uploaded_by_user,
            uploaded_by_device=uploaded_by_device,
        )
        .on_conflict_do_nothing(index_elements=["sha256"])
    )
    return get(db, sha)


def get(db: Session, sha256: str) -> FileInfo:
    row = db.get(StoredFile, sha256)
    if row is None:
        raise AppError(422, "file_not_found")
    return FileInfo(
        row.sha256, row.size_bytes, row.content_type, row.source, row.uploaded_by_user, row.uploaded_by_device
    )
