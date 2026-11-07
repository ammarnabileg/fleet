"""The external services' settings in a transfer file (file storage, WhatsApp, push), by kind. Their secrets travel
only when the user asks, encrypted with a passphrase by app.modules.config_transfer: this module hands them over in
clear inside the server and gets them back the same way. A service the file switches on while its key is missing here
(no secrets in the file, none saved here) is imported switched off, and the report says so; nothing is tried against
the outside services during an import (the panel's test button does that)."""

from pydantic import ValidationError
from sqlalchemy import func

from app.core import crypto
from app.core.errors import AppError
from app.core.transfer import CREATED, UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, each, same
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.integrations import schemas
from app.modules.integrations.models import Connection
from app.modules.integrations.service import Loaded, _cache, _missing, _on, _read

KEY = "integrations"


def _export(ctx: ExportContext) -> dict:
    out, secrets = {}, {}
    for kind in schemas.KINDS:
        row = ctx.db.get(Connection, kind)
        if row is None:
            continue
        loaded = _read(ctx.db, kind)
        out[kind] = {"config": loaded.config.model_dump(mode="json"), "secret_names": sorted(loaded.secrets)}
        if loaded.secrets:
            secrets[kind] = dict(loaded.secrets)
    ctx.put_secrets(KEY, secrets)
    return out


def _off(kind: str, config: dict) -> dict:
    return config | ({"provider": "local"} if kind == "storage" else {"enabled": False})


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db
    if not isinstance(data, dict):
        report.skip("*", "config_section_invalid")
        return
    given = ctx.section_secrets(KEY) or {}

    def one(item):
        kind, entry = item
        if kind not in schemas.KINDS:
            raise AppError(404, "unknown_connection", kind=kind)
        model, secret_names = schemas.KINDS[kind]
        try:
            config = model.model_validate(entry.get("config") or {})
        except ValidationError as exc:
            detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise AppError(422, "invalid_connection", detail=detail) from None
        current = _read(db, kind)
        new_secrets = dict(current.secrets)
        for name, value in (given.get(kind) or {}).items():
            if name in secret_names and isinstance(value, str) and value:
                new_secrets[name] = value
        if _missing(kind, Loaded(0, config, new_secrets)):
            config = model.model_validate(_off(kind, config.model_dump(mode="json")))
            report.warn(kind, "config_integration_off")
        r2_files = files.counts(db)["r2"] if kind == "storage" else 0
        if kind == "storage" and r2_files:
            old = current.config
            moved = old.bucket is not None and any(
                getattr(old, f) != getattr(config, f) for f in ("account_id", "bucket", "jurisdiction")
            )
            if moved or not (new_secrets.get("secret_access_key") and config.access_key_id):
                raise AppError(409, "storage_in_use", count=r2_files)
        stored = config.model_dump(mode="json")
        row = db.get(Connection, kind, with_for_update=True)
        if row is not None and same(current.config.model_dump(mode="json"), stored) and new_secrets == current.secrets:
            return UNCHANGED
        encrypted = {}
        for name, value in new_secrets.items():
            token = row.secrets.get(name) if row is not None else None
            encrypted[name] = token if token and current.secrets.get(name) == value else crypto.encrypt(value)
        if row is None:
            row = Connection(kind=kind, config=stored, secrets=encrypted, version=1)
            db.add(row)
            outcome = CREATED
        else:
            row.config, row.secrets, row.version = stored, encrypted, row.version + 1
            outcome = UPDATED
        row.updated_by, row.updated_at = ctx.actor_user_id, func.now()
        row.checked_at, row.check_ok, row.check_error = None, None, None  # untested here until the panel tries it
        db.flush()
        audit.record(
            db,
            action="integration.changed",
            entity_type="integration",
            entity_id=kind,
            actor_user_id=ctx.actor_user_id,
            before=current.config.model_dump(mode="json") if current.version else None,
            after=stored
            | {"secrets_changed": sorted(n for n in new_secrets if new_secrets[n] != current.secrets.get(n))},
            comment="config import",
        )
        if _on(kind, config):
            report.warn(kind, "config_integration_untested")
        ctx.after_commit.append(lambda k=kind: _cache.pop(k, None))
        return outcome

    each(db, report, sorted(data.items()), lambda i: i[0], one)


SECTIONS_OUT = [
    Section(
        KEY,
        {"ar": "التكاملات (بدون الأسرار إلا بعبارة مرور)", "en": "Integrations (secrets only with a passphrase)"},
        _export,
        _apply,
        order=90,
        has_secrets=True,
    )
]
