"""Uploaded files: stored once, named by their sha256, never modified or deleted by the application.

The type is decided by the file's first bytes, never by its name or the declared content type. Files have no
download endpoint of their own: the module that references a file (a document, an odometer reading) serves it
after checking its own permission and company scope, through response().

The bytes go to the storage chosen in the control panel (the server's disk or a Cloudflare R2 bucket); each row
records where its file is, so a file stays readable after the storage is switched. copy_to_r2 moves the files
written before the switch.
"""

import hashlib
from dataclasses import dataclass

from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import StorageError
from app.modules.files.models import StoredFile
from app.modules.integrations import service as integrations

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
    storage: str = "local"


def read_upload(file) -> bytes:
    """An uploaded file (FastAPI UploadFile), refused beyond the size limit without reading all of it."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, "file_too_large", max_mb=get_settings().max_upload_mb)
    return data


def sniff(data: bytes) -> str | None:
    return next((ctype for magic, ctype in SIGNATURES if data.startswith(magic)), None)


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
    if db.get(StoredFile, sha) is not None:
        return get(db, sha)  # the same file again: its bytes are already stored
    backend = _backend(db)
    try:
        backend.put(sha, data, ctype)
    except StorageError as exc:
        raise AppError(503, "storage_unavailable") from exc
    db.execute(
        insert(StoredFile)
        .values(
            sha256=sha,
            size_bytes=len(data),
            content_type=ctype,
            source=source,
            uploaded_by_user=uploaded_by_user,
            uploaded_by_device=uploaded_by_device,
            storage=backend.name,
        )
        .on_conflict_do_nothing(index_elements=["sha256"])
    )
    return get(db, sha)


def get(db: Session, sha256: str) -> FileInfo:
    row = db.get(StoredFile, sha256)
    if row is None:
        raise AppError(422, "file_not_found")
    return FileInfo(
        row.sha256,
        row.size_bytes,
        row.content_type,
        row.source,
        row.uploaded_by_user,
        row.uploaded_by_device,
        row.storage,
    )


def _backend(db: Session, name: str | None = None):
    try:
        return integrations.storage(db, name)
    except StorageError as exc:
        raise AppError(503, "storage_unavailable") from exc


HEADERS = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"}


def response(db: Session, info: FileInfo):
    """The file's bytes for a download endpoint (after the caller checked who may see it): from the disk, or
    streamed from R2 through the server, so the bucket stays private and every read is checked here."""
    backend = _backend(db, info.storage)
    if info.storage == "local":
        return FileResponse(backend.path(info.sha256), media_type=info.content_type, headers=HEADERS)
    try:
        blob = backend.open(info.sha256)
    except StorageError as exc:
        raise AppError(503, "storage_unavailable") from exc
    headers = HEADERS | {"Content-Length": str(blob.size)}
    return StreamingResponse(blob.chunks, media_type=info.content_type, headers=headers)


def read(db: Session, info: FileInfo) -> bytes:
    try:
        return _backend(db, info.storage).read(info.sha256)
    except (StorageError, OSError) as exc:
        raise AppError(503, "storage_unavailable") from exc


def counts(db: Session) -> dict[str, int]:
    """How many files are on the disk and in R2."""
    rows = db.execute(select(StoredFile.storage, func.count()).group_by(StoredFile.storage))
    return {"local": 0, "r2": 0} | {storage: n for storage, n in rows}


def copy_to_r2(db: Session, *, after: str = "", limit: int = 200) -> dict:
    """Copies a batch of the files written to the disk before R2 was switched on (in sha256 order, after `after`)
    and records each one as in R2 once the bucket holds it with the right size. The disk copies are left for the
    operator to remove. Returns how many were copied, the files missing from the disk (left as they are), the last
    file looked at (the next batch starts after it; None when this was the last batch)."""
    if integrations.load(db, "storage").config.provider != "r2":
        raise AppError(409, "storage_not_r2")
    local, remote = _backend(db, "local"), _backend(db, "r2")
    copied, missing = 0, []
    rows = db.scalars(
        select(StoredFile)
        .where(StoredFile.storage == "local", StoredFile.sha256 > after)
        .order_by(StoredFile.sha256)
        .limit(limit)
    ).all()
    for row in rows:
        if local.size(row.sha256) != row.size_bytes:
            missing.append(row.sha256)
            continue
        try:
            if remote.size(row.sha256) != row.size_bytes:
                remote.put(row.sha256, local.read(row.sha256), row.content_type)
            if remote.size(row.sha256) != row.size_bytes:
                raise StorageError("size mismatch after upload")
        except StorageError as exc:
            db.commit()
            raise AppError(503, "storage_unavailable") from exc
        row.storage = "r2"
        copied += 1
        db.commit()  # one file at a time: an interruption keeps what was done
    last = rows[-1].sha256 if len(rows) == limit else None
    return {"copied": copied, "missing": missing, "last": last}
