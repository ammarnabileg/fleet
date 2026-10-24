"""The driver app's in-app updates. The app is installed from an APK (not from a store), so the server is where a new
version is found: the office uploads the APK the CI built, the server reads its package and versionCode from the
file itself, and publishes it when the office says so. The app asks with its own versionCode and gets the newest
published release, and whether it must update (a release marked required, newer than the app, is published).

The app reports its version as "<name>+<versionCode>" (an older app: the name only, its code unknown); the office
sees how many phones run each release and which drivers are behind.
"""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.app_updates.apk import ApkError
from app.modules.app_updates.apk import read as read_apk
from app.modules.app_updates.models import AppRelease
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.org import service as org
from app.modules.people import service as people

BUILD = re.compile(r"\+(\d{1,9})$")


def build_of(version: str | None) -> int | None:
    """The versionCode in what the app reports ("0.2.0+57" -> 57); None for an older app that sends the name only."""
    m = BUILD.search(version or "")
    return int(m.group(1)) if m else None


def expected_package(db: Session) -> str | None:
    """The package an upload must have: the dashboard's setting, else the server's, else the releases' own."""
    configured = org.get_section(db, "driver_app").android_package or get_settings().android_package
    if configured:
        return configured
    return db.scalar(select(AppRelease.package).order_by(AppRelease.version_code.desc()).limit(1))


def latest_published(db: Session) -> AppRelease | None:
    return db.scalar(
        select(AppRelease).where(AppRelease.status == "published").order_by(AppRelease.version_code.desc()).limit(1)
    )


def _get(db: Session, public_id: uuid.UUID, lock: bool = False) -> AppRelease:
    q = select(AppRelease).where(AppRelease.public_id == public_id)
    row = db.scalar(q.with_for_update() if lock else q)
    if row is None:
        raise AppError(404, "app_release_not_found")
    return row


def _out(r: AppRelease, installed: int = 0) -> dict:
    return {
        "id": str(r.public_id),
        "version_code": r.version_code,
        "version_name": r.version_name,
        "package": r.package,
        "sha256": r.file_sha256,
        "size_bytes": r.size_bytes,
        "notes": r.notes,
        "required": r.required,
        "status": r.status,
        "published_at": r.published_at,
        "created_at": r.created_at,
        "installed": installed,
    }


def _snapshot(r: AppRelease) -> dict:
    return {"version_code": r.version_code, "status": r.status, "required": r.required, "notes": r.notes}


def _clean_notes(db: Session, notes: dict | None) -> dict:
    langs = {x.code for x in i18n.list_languages(db, active_only=False)} | {"ar", "en"}
    out = {}
    for k, v in (notes or {}).items():
        if k not in langs:
            raise AppError(422, "unknown_language", code=k)
        text = (v or "").strip()
        if len(text) > 2000:
            raise AppError(422, "app_release_notes_too_long", max=2000)
        if text:
            out[k] = text
    return out


def upload(db: Session, data: bytes, *, notes: dict | None, actor_user_id: int) -> dict:
    """A new draft from an uploaded APK. Refused: not an APK, another app's package, or a versionCode not above the
    newest published release (Android would not install it over that one)."""
    try:
        info = read_apk(data)
    except ApkError as exc:
        raise AppError(422, exc.code) from None
    package = expected_package(db)
    if package and info.package != package:
        raise AppError(422, "apk_wrong_package", expected=package, got=info.package)
    latest = latest_published(db)
    if latest is not None and info.version_code <= latest.version_code:
        raise AppError(422, "apk_version_not_higher", version_code=info.version_code, latest=latest.version_code)
    if db.scalar(select(AppRelease.id).where(AppRelease.version_code == info.version_code)) is not None:
        raise AppError(409, "app_release_exists", version_code=info.version_code)
    stored = files.store(db, data, source="upload", uploaded_by_user=actor_user_id, apk=True)
    row = AppRelease(
        version_code=info.version_code,
        version_name=info.version_name or str(info.version_code),
        package=info.package,
        file_sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        notes=_clean_notes(db, notes),
        created_by=actor_user_id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "app_release_exists", version_code=info.version_code) from None
    audit.record(
        db,
        action="app_release.uploaded",
        entity_type="app_release",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        after=_snapshot(row) | {"package": row.package, "sha256": row.file_sha256},
    )
    db.commit()
    return _out(row)


def update(db: Session, public_id: uuid.UUID, changes: dict, *, actor_user_id: int) -> dict:
    """The notes, and whether older apps must update."""
    row = _get(db, public_id, lock=True)
    before = _snapshot(row)
    if "notes" in changes and changes["notes"] is not None:
        row.notes = _clean_notes(db, changes["notes"])
    if changes.get("required") is not None:
        row.required = changes["required"]
    audit.record(
        db,
        action="app_release.changed",
        entity_type="app_release",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after=_snapshot(row),
    )
    db.commit()
    return _out(row)


def set_status(db: Session, public_id: uuid.UUID, status: str, *, actor_user_id: int) -> dict:
    row = _get(db, public_id, lock=True)
    if row.status != status:
        before = _snapshot(row)
        row.status = status
        if status == "published":
            row.published_at, row.published_by = utcnow(), actor_user_id
        audit.record(
            db,
            action=f"app_release.{'published' if status == 'published' else 'unpublished'}",
            entity_type="app_release",
            entity_id=row.public_id,
            actor_user_id=actor_user_id,
            before=before,
            after=_snapshot(row),
        )
    db.commit()
    return _out(row)


def delete_draft(db: Session, public_id: uuid.UUID, *, actor_user_id: int) -> None:
    """A draft uploaded by mistake (its file stays in the store, as every stored file does)."""
    row = _get(db, public_id, lock=True)
    if row.status != "draft":
        raise AppError(409, "app_release_published")
    audit.record(
        db,
        action="app_release.deleted",
        entity_type="app_release",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        before=_snapshot(row),
    )
    db.delete(row)
    db.commit()


def overview(db: Session, *, all_companies: bool, company_ids) -> dict:
    """The releases with how many signed-in phones run each, and the drivers in scope with their version."""
    releases = list(db.scalars(select(AppRelease).order_by(AppRelease.version_code.desc())))
    latest = latest_published(db)
    versions = identity.app_versions(db)
    drivers = people.app_drivers(db, all_companies=all_companies, company_ids=company_ids)
    counts: dict[int | None, int] = {}
    rows = []
    for d in drivers:
        if d.id not in versions:
            continue  # no phone signed in: nothing to update
        version, seen = versions[d.id]
        code = build_of(version)
        counts[code] = counts.get(code, 0) + 1
        rows.append(
            {
                "id": str(d.public_id),
                "name": d.name,
                "app_version": version,
                "version_code": code,
                "last_seen_at": seen,
                "outdated": latest is not None and (code is None or code < latest.version_code),
            }
        )
    rows.sort(key=lambda r: (not r["outdated"], r["version_code"] or 0))
    return {
        "package": expected_package(db),
        "max_mb": get_settings().max_apk_mb,
        "latest": latest.version_code if latest else None,
        "releases": [_out(r, counts.get(r.version_code, 0)) for r in releases],
        "unknown_version": counts.get(None, 0),
        "drivers": rows,
    }


def file_of(db: Session, public_id: uuid.UUID) -> tuple[AppRelease, files.FileInfo]:
    row = _get(db, public_id)
    return row, files.get(db, row.file_sha256)


# ------------------------------------------------------------------ the app


def _notes_for(notes: dict, lang: str | None) -> str | None:
    for code in (lang, "en", "ar"):
        if code and notes.get(code):
            return notes[code]
    return next(iter(notes.values()), None)


def check(db: Session, version_code: int, lang: str | None) -> dict:
    """What the app asks with its own versionCode: the newest published release above it (or none) and whether it
    must update (a published release marked required is above it)."""
    latest = latest_published(db)
    if latest is None or latest.version_code <= version_code:
        return {"latest": None, "required": False}
    required = (
        db.scalar(
            select(func.count()).where(
                AppRelease.status == "published", AppRelease.required.is_(True), AppRelease.version_code > version_code
            )
        )
        > 0
    )
    return {
        "latest": {
            "version_code": latest.version_code,
            "version_name": latest.version_name,
            "size": latest.size_bytes,
            "sha256": latest.file_sha256,
            "notes": _notes_for(latest.notes, lang),
            "url": f"/api/v1/driver/app-update/{latest.version_code}.apk",
        },
        "required": required,
    }


def published_file(db: Session, version_code: int) -> files.FileInfo:
    row = db.scalar(select(AppRelease).where(AppRelease.version_code == version_code, AppRelease.status == "published"))
    if row is None:
        raise AppError(404, "app_release_not_found")
    return files.get(db, row.file_sha256)
