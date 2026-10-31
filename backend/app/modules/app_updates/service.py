"""The driver app's in-app updates. The app is installed from an APK (not from a store), so the server is where a new
version is found: the office uploads the APK the CI built, the server reads its package and versionCode from the
file itself, and publishes it when the office says so. The app asks with its own versionCode and gets the newest
published release, and whether it must update (a release marked required, newer than the app, is published).

The app reports its version as "<name>+<versionCode>" (an older app: the name only, its code unknown); the office
sees how many phones run each release and which drivers are behind.

«تحديث التطبيق» (the settings section app_update) names the version announced to the apps and whether it is forced;
saving it publishes that release and writes the same values to Firebase Remote Config (when push is set up), which
the app reads first, falling back to this server's check. Left empty, the newest published release is announced,
as before. A release also comes from the repository's GitHub releases (github.py), imported as a draft: announcing it
and forcing it stay the office's decisions. The public link /app/download serves the announced release's file from
our own store under our own address.
"""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import remote_config as rc
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.app_updates.apk import ApkError
from app.modules.app_updates.apk import read as read_apk
from app.modules.app_updates.models import AppRelease, AppUpdateState
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.integrations import service as integrations
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
        "origin": r.origin,
        "github_tag": r.github_tag,
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


def store_release(
    db: Session,
    data: bytes,
    *,
    notes: dict | None,
    actor_user_id: int | None,
    origin: str = "upload",
    github_tag: str | None = None,
) -> AppRelease:
    """A new draft from an APK (uploaded, or imported from GitHub), in the caller's transaction. Refused: not an
    APK, another app's package, or a versionCode not above the newest published release (Android would not install
    it over that one)."""
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
        origin=origin,
        github_tag=github_tag,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "app_release_exists", version_code=info.version_code) from None
    audit.record(
        db,
        action="app_release.uploaded" if origin == "upload" else "app_release.imported",
        entity_type="app_release",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        after=_snapshot(row) | {"package": row.package, "sha256": row.file_sha256, "origin": origin},
    )
    return row


def upload(db: Session, data: bytes, *, notes: dict | None, actor_user_id: int) -> dict:
    row = store_release(db, data, notes=notes, actor_user_id=actor_user_id)
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
    sync_remote(db)
    return _out(row)


def _publish(db: Session, row: AppRelease, actor_user_id: int | None) -> None:
    before = _snapshot(row)
    row.status = "published"
    row.published_at, row.published_by = utcnow(), actor_user_id
    audit.record(
        db,
        action="app_release.published",
        entity_type="app_release",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after=_snapshot(row),
    )


def set_status(db: Session, public_id: uuid.UUID, status: str, *, actor_user_id: int) -> dict:
    """Publish or unpublish. The release «تحديث التطبيق» announces cannot be unpublished (announce another first);
    one published above it becomes the announced one (the office published it to have drivers on it)."""
    row = _get(db, public_id, lock=True)
    settings = org.section_now(db, "app_update")
    if row.status != status:
        if status == "published":
            _publish(db, row, actor_user_id)
        else:
            if settings.version_code == row.version_code:
                raise AppError(409, "app_release_announced", version_code=row.version_code)
            before = _snapshot(row)
            row.status = "draft"
            audit.record(
                db,
                action="app_release.unpublished",
                entity_type="app_release",
                entity_id=row.public_id,
                actor_user_id=actor_user_id,
                before=before,
                after=_snapshot(row),
            )
    db.commit()
    if status == "published" and settings.version_code is not None and row.version_code > settings.version_code:
        version, current = org.section_version(db, "app_update")
        org.update_section(
            db,
            "app_update",
            current.model_dump(mode="json") | {"latest_version": _version_text(row)},
            expected_version=version,
            actor_user_id=actor_user_id,
        )
    sync_remote(db)
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


def announced(db: Session) -> tuple[AppRelease | None, bool]:
    """The release the apps are told to update to, and whether «تحديث التطبيق» forces it: the version named there
    (published when it was saved), else the newest published release."""
    settings = org.get_section(db, "app_update")
    if settings.version_code is not None:
        row = db.scalar(
            select(AppRelease).where(AppRelease.version_code == settings.version_code, AppRelease.status == "published")
        )
        if row is not None:
            return row, settings.force_update
    return latest_published(db), False


def check(db: Session, version_code: int, lang: str | None) -> dict:
    """What the app asks with its own versionCode: the announced release when it is above it (or none) and whether
    it must update (forced in «تحديث التطبيق», or a published release marked required is above the app, up to the
    announced one)."""
    latest, forced = announced(db)
    if latest is None or latest.version_code <= version_code:
        return {"latest": None, "required": False}
    required = (
        forced
        or db.scalar(
            select(func.count()).where(
                AppRelease.status == "published",
                AppRelease.required.is_(True),
                AppRelease.version_code > version_code,
                AppRelease.version_code <= latest.version_code,
            )
        )
        > 0
    )
    settings = org.get_section(db, "app_update")
    pinned_notes = settings.notes if settings.version_code == latest.version_code else ""
    return {
        "latest": {
            "version_code": latest.version_code,
            "version_name": latest.version_name,
            "size": latest.size_bytes,
            "sha256": latest.file_sha256,
            "notes": _notes_for(latest.notes, lang) or pinned_notes or None,
            "url": f"/api/v1/driver/app-update/{latest.version_code}.apk",
        },
        "required": required,
    }


def published_file(db: Session, version_code: int) -> files.FileInfo:
    row = db.scalar(select(AppRelease).where(AppRelease.version_code == version_code, AppRelease.status == "published"))
    if row is None:
        raise AppError(404, "app_release_not_found")
    return files.get(db, row.file_sha256)


# ------------------------------------------------------------------ «تحديث التطبيق» and Firebase Remote Config

VERSION_TEXT = re.compile(r"^\d{1,3}\.\d{1,3}\.(\d{1,10})$")


def _version_text(row: AppRelease) -> str:
    """How a release is written in latest_version: its name when it is the CI's "0.1.1057" (ending with its
    versionCode), else the versionCode alone."""
    m = VERSION_TEXT.match(row.version_name)
    return row.version_name if m and int(m.group(1)) == row.version_code else str(row.version_code)


def download_url(version: str | None = None) -> str:
    """The public link on our own address (never GitHub's or Firebase's)."""
    base = get_settings().public_url.rstrip("/") + "/app/download"
    return f"{base}/{version}" if version else base


def _state(db: Session, lock: bool = False) -> AppUpdateState:
    q = select(AppUpdateState).where(AppUpdateState.id == 1)
    row = db.scalar(q.with_for_update() if lock else q)
    if row is None:
        db.execute(pg_insert(AppUpdateState).values(id=1).on_conflict_do_nothing())
        row = db.scalar(q.with_for_update() if lock else q)
    return row


PARAMETERS = {
    "driver_latest_version_code": ("NUMBER", "The driver app's announced versionCode (0: none)"),
    "driver_latest_version_name": ("STRING", "The driver app's announced version name"),
    "driver_force_update": ("BOOLEAN", "Older driver apps must update before they can be used"),
    "driver_download_url": ("STRING", "The public download link of the announced driver app"),
    "driver_update_notes": ("STRING", "What is new, from the dashboard"),
}


def remote_values(db: Session) -> dict[str, str]:
    """What Remote Config carries: the same answer the server's check gives an app older than the announced one."""
    row, forced = announced(db)
    return {
        "driver_latest_version_code": str(row.version_code) if row else "0",
        "driver_latest_version_name": row.version_name if row else "",
        "driver_force_update": "true" if row is not None and (forced or row.required) else "false",
        "driver_download_url": download_url(),
        "driver_update_notes": org.get_section(db, "app_update").notes,
    }


def publish_remote(db: Session) -> dict:
    """Writes the values to Firebase Remote Config when push's service account is set up; the outcome is kept
    for the panel (published, failed with Google's reason, or not configured). Never raises."""
    values = remote_values(db)
    client = integrations.remote_config(db)
    state = _state(db, lock=True)
    state.remote_at = utcnow()
    if client is None:
        state.remote_state, state.remote_error = "not_configured", None
    else:
        try:
            client.publish({k: (values[k], *PARAMETERS[k]) for k in PARAMETERS})
            state.remote_state, state.remote_error, state.remote_values = "published", None, values
        except rc.RemoteConfigError as exc:
            state.remote_state, state.remote_error = "failed", str(exc)[:500]
    db.commit()
    return _remote_out(db, state)


def sync_remote(db: Session) -> None:
    """After a release changed: Remote Config is written again only if what it carries changed (or the last
    try failed), so publishing a draft nobody announces costs no request to Google."""
    state = _state(db)
    if state.remote_state == "published" and state.remote_values == remote_values(db):
        return
    if state.remote_state in ("published", "failed") or integrations.remote_config(db) is not None:
        publish_remote(db)


def _remote_out(db: Session, state: AppUpdateState) -> dict:
    return {
        "configured": integrations.remote_config(db) is not None,
        "state": state.remote_state,
        "error": state.remote_error,
        "at": state.remote_at,
        "values": state.remote_values,
    }


def settings_out(db: Session) -> dict:
    version, value = org.section_version(db, "app_update")
    state = _state(db)
    db.commit()
    row, forced = announced(db)
    repo, token = github_source(db)
    return {
        "version": version,
        "value": value.model_dump(mode="json"),
        "download_url": download_url(),
        "announced": None
        if row is None
        else {
            "version_code": row.version_code,
            "version_name": row.version_name,
            "forced": forced or row.required,
            "size_bytes": row.size_bytes,
            "published_at": row.published_at,
        },
        "remote": _remote_out(db, state),
        "github": {
            "repo": repo,
            "token": bool(token),
            "state": state.github_state,
            "error": state.github_error,
            "release": state.github_release,
            "at": state.github_at,
        },
    }


def save_settings(db: Session, value: dict, *, expected_version: int, actor_user_id: int) -> dict:
    """Saves «تحديث التطبيق»: the release named must be in «تحديثات التطبيق» (a draft is published now), then the
    values go to Firebase Remote Config. A failed Remote Config write keeps the save (the server's own check
    answers the apps already) and shows its reason."""
    new = org.parse_section("app_update", value)
    if new.version_code is not None:
        row = db.scalar(select(AppRelease).where(AppRelease.version_code == new.version_code).with_for_update())
        if row is None:
            raise AppError(422, "app_update_release_missing", version_code=new.version_code)
        if row.status != "published":
            _publish(db, row, actor_user_id)  # committed with the settings below
    org.update_section(
        db, "app_update", new.model_dump(mode="json"), expected_version=expected_version, actor_user_id=actor_user_id
    )
    publish_remote(db)
    return settings_out(db)


def github_source(db: Session) -> tuple[str, str]:
    """The repository whose releases are imported (the dashboard's, else the server's) and its token (server only)."""
    s = get_settings()
    return org.get_section(db, "app_update").github_repo or s.github_releases_repo, s.github_token


# ------------------------------------------------------------------ the public download link


def download_info(db: Session) -> dict:
    row, forced = announced(db)
    name = org.get_section(db, "app_update").download_name
    return {
        "release": None
        if row is None
        else {
            "version_code": row.version_code,
            "version_name": row.version_name,
            "size_bytes": row.size_bytes,
            "sha256": row.file_sha256,
            "published_at": row.published_at,
            "forced": forced or row.required,
            "file_name": f"{name}-{row.version_name}.apk",
        },
        "url": download_url(),
        "version_url": download_url(row.version_name) if row else None,
    }


def public_file(db: Session, version: str | None) -> tuple[files.FileInfo, str]:
    """The announced release's APK (or a published one by its name or versionCode), from our own store, with the
    name it is saved as on the phone."""
    if version is None:
        row = announced(db)[0]
    else:
        q = select(AppRelease).where(AppRelease.status == "published")
        if version.isdigit() and len(version) <= 10:
            q = q.where((AppRelease.version_name == version) | (AppRelease.version_code == int(version)))
        else:
            q = q.where(AppRelease.version_name == version)
        row = db.scalar(q.order_by(AppRelease.version_code.desc()).limit(1))
    if row is None:
        raise AppError(404, "app_release_not_found")
    name = org.get_section(db, "app_update").download_name
    return files.get(db, row.file_sha256), f"{name}-{row.version_name}.apk"
