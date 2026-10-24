"""Configuration export and import (the integrations page's «نقل الإعدادات»)."""

import json
from datetime import date

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.config_transfer import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import Principal, require_permission

router = APIRouter(prefix="/api/v1", tags=["config"])


def _keys(raw: str | None) -> list[str] | None:
    keys = [k.strip() for k in (raw or "").split(",") if k.strip()]
    return keys or None


def _file(doc: dict) -> Response:
    body = json.dumps(doc, ensure_ascii=False, indent=1, default=str)
    name = f"fleet-config-{date.today().isoformat()}.json"
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


def _visible(principal: Principal, keys: list[str] | None) -> list[str] | None:
    """The integrations' settings (without their secrets, still the bucket and the accounts) are for whoever manages
    the integrations: left out of an export of everything, refused when asked for by name."""
    if principal.has("integrations.manage"):
        return keys
    if keys is None:
        return [s["key"] for s in service.sections() if s["key"] != "integrations"]
    if "integrations" in keys:
        raise AppError(403, "permission_denied", permission="integrations.manage")
    return keys


def _owner(principal: Principal) -> None:
    if not principal.all_permissions:
        raise AppError(403, "config_owner_only")


@router.get("/config/sections", response_model=list[schemas.SectionOut])
def list_sections(_: Principal = Depends(require_permission("settings.view"))):
    return service.sections()


@router.get("/config/export")
def export(
    request: Request,
    sections: str | None = None,
    principal: Principal = Depends(require_permission("settings.view")),
    db: Session = Depends(get_session),
):
    """The configuration as a JSON file, without any secret (comma-separated section keys; none: every section)."""
    keys = _visible(principal, _keys(sections))
    doc = service.export(db, keys, source=request.url.hostname, actor_user_id=principal.user_id)
    return _file(doc)


@router.post("/config/export")
def export_with_options(
    request: Request,
    body: schemas.ExportIn,
    principal: Principal = Depends(require_permission("settings.view")),
    db: Session = Depends(get_session),
):
    """As GET, and with include_secrets the integrations' secrets sealed with the passphrase (owner only)."""
    if body.include_secrets:
        _owner(principal)
        if not body.passphrase:
            raise AppError(422, "config_passphrase_short", min=service.sealed.MIN_PASSPHRASE)
    doc = service.export(
        db,
        _visible(principal, body.sections or None),
        source=request.url.hostname,
        actor_user_id=principal.user_id,
        passphrase=body.passphrase if body.include_secrets else None,
    )
    return _file(doc)


@router.post("/config/import", response_model=schemas.ImportOut)
def import_config(
    file: UploadFile,
    dry_run: bool = Form(True),
    passphrase: str | None = Form(None),
    sections: str | None = Form(None),
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    """dry_run (the default): what the import would do, section by section, and nothing is saved. Then the same
    file with dry_run=false applies it in one transaction. Merge only: nothing missing from the file is deleted."""
    _owner(principal)
    doc = service.parse(files.read_upload(file, max_mb=service.MAX_MB))
    return service.run_import(
        db,
        doc,
        keys=_keys(sections),
        passphrase=passphrase or None,
        dry_run=dry_run,
        actor_user_id=principal.user_id,
    )
