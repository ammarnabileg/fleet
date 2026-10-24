"""Configuration export and import (JSON), to move what an office set up on one installation (a test server) to
another (production). The sections are the modules' own (their transfer.py, see app.core.transfer); this module
writes the file, reads it back, checks its format version, seals or opens the secrets and runs an import in one
transaction: a dry run applies everything and rolls it back, so its report is exactly what the import will do.

The file: {"format": "fleet-config", "version": 1, "exported_at", "app_version", "source", "sections": {key: data},
"files": {sha256: {content_type, data (base64)}}, "secrets": null | sealed box}. It never holds a secret in clear,
users or their passwords, or operational data (employees, vehicles, money, reports)."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.transfer import ExportContext, ImportContext, Report, Section
from app.modules.approvals import transfer as approvals
from app.modules.attendance import transfer as attendance
from app.modules.audit import service as audit
from app.modules.config_transfer import sealed
from app.modules.documents import transfer as documents
from app.modules.driver_status import transfer as driver_status
from app.modules.finance import transfer as finance
from app.modules.i18n import transfer as i18n
from app.modules.identity import transfer as identity
from app.modules.integrations import transfer as integrations
from app.modules.maintenance import transfer as maintenance
from app.modules.org import transfer as org
from app.modules.payroll import transfer as payroll
from app.modules.people import transfer as people

log = logging.getLogger("fleet.config_transfer")

FORMAT, VERSION = "fleet-config", 1
MAX_MB = 60


def registry() -> list[Section]:
    modules = (i18n, org, people, documents, attendance, identity, finance, payroll, approvals, maintenance)
    found = [s for m in (*modules, driver_status, integrations) for s in m.SECTIONS_OUT]
    return sorted(found, key=lambda s: (s.order, s.key))


def sections() -> list[dict]:
    return [{"key": s.key, "label": s.label, "has_secrets": s.has_secrets} for s in registry()]


def _chosen(keys: list[str] | None) -> list[Section]:
    every = registry()
    if not keys:
        return every
    unknown = sorted(set(keys) - {s.key for s in every})
    if unknown:
        raise AppError(422, "config_section_unknown", sections=", ".join(unknown))
    return [s for s in every if s.key in set(keys)]


# ------------------------------------------------------------------ export


def export(
    db: Session,
    keys: list[str] | None,
    *,
    source: str | None,
    actor_user_id: int,
    passphrase: str | None = None,
) -> dict:
    """The file for the chosen sections (all when none). With a passphrase, the secrets are sealed with it; without,
    the file has none (the services' non-secret settings only)."""
    from app.main import VERSION as APP_VERSION

    chosen = _chosen(keys)
    ctx = ExportContext(db, include_secrets=bool(passphrase))
    out = {}
    for s in chosen:
        data = s.export(ctx)
        if data is not None:
            out[s.key] = data
    box = sealed.seal(ctx.secrets, passphrase) if passphrase and ctx.secrets else None
    if passphrase and not ctx.secrets:
        box = sealed.seal({}, passphrase)  # asked for: the file says so, even with nothing to seal
    doc = {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "source": source,
        "sections": out,
        "files": ctx.files,
        "secrets": box,
    }
    audit.record(
        db,
        action="config.exported",
        entity_type="config",
        actor_user_id=actor_user_id,
        after={"sections": sorted(out), "secrets": box is not None, "files": len(ctx.files)},
    )
    db.commit()
    return doc


# ------------------------------------------------------------------ import


def parse(data: bytes) -> dict:
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise AppError(422, "config_file_invalid") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("sections"), dict):
        raise AppError(422, "config_file_invalid")
    version = doc.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise AppError(422, "config_file_invalid")
    if version > VERSION:
        raise AppError(422, "config_version_newer", version=version, supported=VERSION)
    return doc


def run_import(
    db: Session,
    doc: dict,
    *,
    keys: list[str] | None,
    passphrase: str | None,
    dry_run: bool,
    actor_user_id: int,
) -> dict:
    """Applies the file's sections (the chosen ones, else all it has) in one transaction, in the order the sections
    depend on each other. Merge only: created when missing, updated when different, never deleted. A dry run rolls
    everything back."""
    known = {s.key: s for s in registry()}
    in_file = doc["sections"]
    unknown = sorted(k for k in in_file if k not in known)
    wanted = [s for s in registry() if s.key in in_file and (not keys or s.key in keys)]
    secrets, secrets_state = None, "none"
    if doc.get("secrets"):
        if passphrase:
            secrets, secrets_state = sealed.unseal(doc["secrets"], passphrase), "used"
        else:
            secrets_state = "skipped"  # the file has them, no passphrase given: imported without them
    ctx = ImportContext(db, actor_user_id, files=doc.get("files") or {}, secrets=secrets)
    reports: dict[str, Report] = {}
    try:
        for s in wanted:
            report = reports[s.key] = Report()
            s.apply(ctx, in_file[s.key], report)
        summary = {
            "sections": {
                k: {"created": r.created, "updated": r.updated, "skipped": len(r.skipped)} for k, r in reports.items()
            },
            "source": doc.get("source"),
            "exported_at": doc.get("exported_at"),
            "secrets": secrets_state,
        }
        audit.record(db, action="config.imported", entity_type="config", actor_user_id=actor_user_id, after=summary)
        db.flush()
    except Exception:
        db.rollback()
        raise
    if dry_run:
        db.rollback()
    else:
        db.commit()
        for fn in ctx.after_commit:
            try:
                fn()
            except Exception:  # noqa: BLE001 - a cache or a live notice, never the import itself
                log.exception("after config import")
    labels = {s.key: s.label for s in registry()}
    return {
        "dry_run": dry_run,
        "format_version": doc["version"],
        "source": doc.get("source"),
        "exported_at": doc.get("exported_at"),
        "app_version": doc.get("app_version"),
        "secrets": secrets_state,
        "unknown_sections": unknown,
        "sections": [{"key": k, "label": labels[k]} | r.out() for k, r in reports.items()],
    }
