"""The driver app's releases from the repository's GitHub releases: the CI publishes each signed build of the
deployed branch as a release named exactly its version ("0.1.1057", tag "v0.1.1057") with one asset, "0.1.1057.apk".

Importing reads the latest release through the GitHub API (a token only for a private repository), downloads its
APK once into our own file store, checks it like an upload (package, versionCode above the published ones) and keeps
it as a draft. Announcing it in «تحديث التطبيق» and forcing it stay the office's decisions; the drivers and the public
download link get the file from our server, never from GitHub."""

import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.app_updates import service
from app.modules.app_updates.models import AppRelease

API = "https://api.github.com"
CODE = re.compile(r"(?:^|\.)(\d{1,10})\.apk$")


def _transport():
    """The HTTP transport for GitHub; None is the real network (tests put a fake here)."""
    return None


def _client(token: str) -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "fleet"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # redirects followed: an asset is served from GitHub's storage host, and httpx drops the token on another host
    return httpx.Client(timeout=60.0, headers=headers, follow_redirects=True, transport=_transport())


def _pick_asset(release: dict) -> dict:
    """The APK named as the release ("0.1.1057.apk"), else the only APK attached."""
    apks = [a for a in release.get("assets") or [] if str(a.get("name", "")).lower().endswith(".apk")]
    names = {f"{release.get('name') or ''}.apk", f"{str(release.get('tag_name') or '').lstrip('v')}.apk"}
    named = [a for a in apks if a["name"] in names]
    if named:
        return named[0]
    if len(apks) == 1:
        return apks[0]
    raise AppError(422, "github_no_apk", tag=release.get("tag_name") or "")


def _download(client: httpx.Client, asset: dict) -> bytes:
    limit = get_settings().max_apk_mb * 1024 * 1024
    if int(asset.get("size") or 0) > limit:
        raise AppError(413, "file_too_large", max_mb=get_settings().max_apk_mb)
    out = bytearray()
    with client.stream("GET", asset["url"], headers={"Accept": "application/octet-stream"}) as r:
        if r.status_code != 200:
            raise AppError(502, "github_unreachable", status=r.status_code)
        for chunk in r.iter_bytes():
            out += chunk
            if len(out) > limit:
                raise AppError(413, "file_too_large", max_mb=get_settings().max_apk_mb)
    return bytes(out)


def _record(db: Session, state: str, *, error: str | None = None, release: str | None = None) -> None:
    row = service._state(db, lock=True)
    row.github_state, row.github_error, row.github_at = state, error, utcnow()
    if release is not None:
        row.github_release = release
    db.commit()


def import_latest(db: Session, *, actor_user_id: int | None) -> dict:
    """The latest GitHub release as a draft release. Already imported (or uploaded): nothing downloaded again."""
    repo, token = service.github_source(db)
    if not repo:
        raise AppError(422, "github_not_configured")
    try:
        with _client(token) as client:
            r = client.get(f"{API}/repos/{repo}/releases/latest")
            if r.status_code == 404:
                raise AppError(404, "github_no_release", repo=repo)
            if r.status_code != 200:
                raise AppError(502, "github_unreachable", status=r.status_code)
            release = r.json()
            tag = str(release.get("tag_name") or "")
            asset = _pick_asset(release)
            m = CODE.search(asset["name"])
            named_code = int(m.group(1)) if m else None
            if named_code is not None:
                existing = db.scalar(select(AppRelease).where(AppRelease.version_code == named_code))
                if existing is not None:
                    _record(db, "up_to_date", release=release.get("name") or tag)
                    return {"created": False, "release": service._out(existing), "tag": tag}
            data = _download(client, asset)
    except httpx.HTTPError:
        _record(db, "failed", error="github_unreachable")
        raise AppError(502, "github_unreachable", status=0) from None
    except AppError as exc:
        db.rollback()
        _record(db, "failed", error=exc.code)
        raise
    try:
        info = service.read_apk(data)
        if named_code is not None and info.version_code != named_code:
            raise AppError(422, "github_apk_mismatch", name=asset["name"], version_code=info.version_code)
        row = service.store_release(db, data, notes=None, actor_user_id=actor_user_id, origin="github", github_tag=tag)
    except service.ApkError as exc:
        db.rollback()
        _record(db, "failed", error=exc.code)
        raise AppError(422, exc.code) from None
    except AppError as exc:
        db.rollback()
        _record(db, "failed", error=exc.code)
        raise
    db.commit()
    out = service._out(row)
    _record(db, "imported", release=release.get("name") or tag)
    return {"created": True, "release": out, "tag": tag}


def auto_import(db: Session) -> bool:
    """The hourly job: only when the dashboard asks for it and a repository is named. True: a new draft."""
    if not service.org.get_section(db, "app_update").github_auto_import or not service.github_source(db)[0]:
        return False
    try:
        return import_latest(db, actor_user_id=None)["created"]
    except AppError:
        return False  # kept in the state the panel shows
