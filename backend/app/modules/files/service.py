"""Uploaded files: stored once, named by their sha256, never modified or deleted by the application.

The type is decided by the file's first bytes, never by its name or the declared content type. Files have no
download endpoint of their own: the module that references a file (a document, an odometer reading) serves it
after checking its own permission and company scope, through response().

The bytes go where the control panel says (the server's disk, a Cloudflare R2 bucket, or both); each row records
which copies exist, and a file is read from wherever a copy is: the disk first, else R2. sync() copies the files
each way the choice asks (to R2, to the disk, or both), so the choice can be changed at any time, and a second
server on the same database reads the files through R2.
"""

import hashlib
import logging
import time
from dataclasses import dataclass

from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import LocalStorage, StorageError
from app.modules.files.models import StoredFile
from app.modules.integrations import service as integrations

log = logging.getLogger("fleet.files")

SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)
IMAGES = {"image/jpeg", "image/png"}
APK = "application/vnd.android.package-archive"  # stored only through store(apk=True): the app's own releases


@dataclass(frozen=True)
class FileInfo:
    sha256: str
    size_bytes: int
    content_type: str
    source: str
    uploaded_by_user: int | None
    uploaded_by_device: int | None
    on_disk: bool = True
    in_r2: bool = False


def read_upload(file, max_mb: int | None = None) -> bytes:
    """An uploaded file (FastAPI UploadFile), refused beyond the size limit without reading all of it."""
    max_mb = max_mb or get_settings().max_upload_mb
    limit = max_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, "file_too_large", max_mb=max_mb)
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
    apk: bool = False,
) -> FileInfo:
    """Writes the file (if new) and adds its row to the caller's transaction. apk: an Android package (the caller
    has read its manifest), with its own size limit; nothing else is accepted then."""
    if not data:
        raise AppError(422, "file_empty")
    max_mb = get_settings().max_apk_mb if apk else get_settings().max_upload_mb
    if len(data) > max_mb * 1024 * 1024:
        raise AppError(413, "file_too_large", max_mb=max_mb)
    ctype = (APK if data.startswith(b"PK\x03\x04") else None) if apk else sniff(data)
    if ctype is None or (images_only and ctype not in IMAGES):
        raise AppError(415, "file_type_not_allowed")
    sha = hashlib.sha256(data).hexdigest()
    if db.get(StoredFile, sha) is not None:
        return get(db, sha)  # the same file again: its bytes are already stored
    where = integrations.storage_mode(db)
    on_disk = in_r2 = False
    if where in ("local", "both"):
        try:
            _disk().put(sha, data, ctype)
        except OSError as exc:
            raise AppError(503, "storage_unavailable") from exc
        on_disk = True
    if where in ("r2", "both"):
        try:
            _backend(db, "r2").put(sha, data, ctype)
            in_r2 = True
        except (StorageError, AppError) as exc:
            if not on_disk:
                raise AppError(503, "storage_unavailable") from exc
            log.warning("file %s kept on the disk only, R2 refused it: %s", sha, exc)  # the next sync copies it
    db.execute(
        insert(StoredFile)
        .values(
            sha256=sha,
            size_bytes=len(data),
            content_type=ctype,
            source=source,
            uploaded_by_user=uploaded_by_user,
            uploaded_by_device=uploaded_by_device,
            on_disk=on_disk,
            in_r2=in_r2,
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
        row.on_disk,
        row.in_r2,
    )


def _disk() -> LocalStorage:
    return LocalStorage(get_settings().files_dir)


def _backend(db: Session, name: str):
    try:
        return integrations.storage(db, name)
    except StorageError as exc:
        raise AppError(503, "storage_unavailable") from exc


def _on_this_disk(info: FileInfo) -> bool:
    """A copy of the whole file on this server's disk (whatever the row says: another server may have written it)."""
    return _disk().size(info.sha256) == info.size_bytes


HEADERS = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"}


def response(db: Session, info: FileInfo, *, filename: str | None = None, headers: dict | None = None):
    """The file's bytes for a download endpoint (after the caller checked who may see it): from this server's disk
    when a copy is there, else streamed from R2 through the server, so the bucket stays private and every read is
    checked here. From the disk a Range request gets its part (206), so a large download can resume."""
    headers = HEADERS | (headers or {})
    if _on_this_disk(info):
        return FileResponse(_disk().path(info.sha256), media_type=info.content_type, headers=headers, filename=filename)
    if not info.in_r2:
        raise AppError(503, "storage_unavailable")  # on another server's disk only, not copied to R2 yet
    try:
        blob = _backend(db, "r2").open(info.sha256)
    except StorageError as exc:
        raise AppError(503, "storage_unavailable") from exc
    headers = headers | {"Content-Length": str(blob.size)}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return StreamingResponse(blob.chunks, media_type=info.content_type, headers=headers)


def read(db: Session, info: FileInfo) -> bytes:
    try:
        if _on_this_disk(info):
            return _disk().read(info.sha256)
        if info.in_r2:
            return _backend(db, "r2").read(info.sha256)
    except (StorageError, OSError) as exc:
        raise AppError(503, "storage_unavailable") from exc
    raise AppError(503, "storage_unavailable")


def counts(db: Session) -> dict[str, int]:
    """How many files have a copy on the disk, in R2, and how many each background copy still has to do."""
    total, disk, r2, to_r2, to_disk = db.execute(
        select(
            func.count(),
            func.count().filter(StoredFile.on_disk),
            func.count().filter(StoredFile.in_r2),
            func.count().filter(StoredFile.on_disk, ~StoredFile.in_r2),
            func.count().filter(StoredFile.in_r2, ~StoredFile.on_disk),
        )
    ).one()
    return {"total": total, "local": disk, "r2": r2, "to_r2": to_r2, "to_disk": to_disk}


def directions(db: Session) -> tuple[str, ...]:
    """Which ways the files are copied for the storage chosen: R2 alone, every file to R2; the disk alone, every file
    back to the disk (while R2 is still set up); both, each way."""
    where = integrations.storage_mode(db)
    if where == "r2":
        return ("to_r2",)
    if not integrations.r2_ready(db):
        return ()
    return ("to_disk",) if where == "local" else ("to_r2", "to_disk")


def sync(db: Session, direction: str, *, after: str = "", limit: int = 200) -> dict:
    """Copies a batch of files one way (in sha256 order, after `after`) and records each copy once it holds the whole
    file. Nothing is ever deleted: a file copied keeps its other copy. Returns how many were copied, the files with
    no copy to read from (left as they are), and the last file looked at (the next batch starts after it; None when
    this was the last batch)."""
    if direction not in directions(db):
        raise AppError(409, "storage_sync_off", direction=direction)
    disk, remote = _disk(), _backend(db, "r2")
    to_r2 = direction == "to_r2"
    pending = (StoredFile.on_disk & ~StoredFile.in_r2) if to_r2 else (StoredFile.in_r2 & ~StoredFile.on_disk)
    rows = db.scalars(
        select(StoredFile).where(pending, StoredFile.sha256 > after).order_by(StoredFile.sha256).limit(limit)
    ).all()
    copied, missing = 0, []
    source, target = (disk, remote) if to_r2 else (remote, disk)
    for row in rows:
        try:
            if target.size(row.sha256) != row.size_bytes:  # already there (an operator's copy): only recorded
                if source.size(row.sha256) != row.size_bytes:
                    missing.append(row.sha256)
                    continue
                target.put(row.sha256, source.read(row.sha256), row.content_type)
            if target.size(row.sha256) != row.size_bytes:
                raise StorageError("size mismatch after copying")
        except (StorageError, OSError) as exc:
            db.commit()
            raise AppError(503, "storage_unavailable") from exc
        if to_r2:
            row.in_r2 = True
        else:
            row.on_disk = True
        copied += 1
        db.commit()  # one file at a time: an interruption keeps what was done
    last = rows[-1].sha256 if len(rows) == limit else None
    return {"copied": copied, "missing": missing, "last": last}


def run_sync(db, seconds: float) -> dict[str, int]:
    """Copies the files each way the chosen storage asks (to R2, back to the disk, or both), for at most `seconds`;
    what is left waits for the next run. Returns how many were copied each way."""
    copied: dict[str, int] = {}
    deadline = time.monotonic() + seconds
    for direction in directions(db):
        after, copied[direction] = "", 0
        while time.monotonic() < deadline:
            try:
                out = sync(db, direction, after=after)
            except AppError as exc:
                log.warning("copying files %s stopped: %s", direction, exc.code)
                break
            copied[direction] += out["copied"]
            if out["missing"]:
                log.warning("files with no copy to read from, left as they are: %s", out["missing"])
            if out["last"] is None:
                break
            after = out["last"]
    return copied
