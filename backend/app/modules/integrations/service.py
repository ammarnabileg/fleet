import logging
import time
from dataclasses import dataclass

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core import crypto, messaging
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import LocalStorage, R2Storage, StorageError
from app.modules.audit import service as audit
from app.modules.integrations import schemas
from app.modules.integrations.models import Connection

log = logging.getLogger("fleet.integrations")

# One relay pass: claim unpublished events without blocking other relays, fan them out to the
# matching subscriptions, mark them published. All in the caller's transaction (tested: T-OUT-01).
_RELAY = text("""
    WITH picked AS (
        SELECT id, event_id, event_type
        FROM integrations.outbox
        WHERE published_at IS NULL
        ORDER BY id
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    ), fanout AS (
        INSERT INTO integrations.deliveries (event_id, subscription_id)
        SELECT p.event_id, s.id
        FROM picked p
        JOIN integrations.subscriptions s ON s.active AND p.event_type = ANY (s.event_types)
        ON CONFLICT DO NOTHING
    )
    UPDATE integrations.outbox o
    SET published_at = now()
    FROM picked p
    WHERE o.id = p.id
    RETURNING o.id
""")


def relay_once(db: Session, limit: int = 100) -> int:
    published = len(db.execute(_RELAY, {"limit": limit}).all())
    db.commit()
    return published


def already_processed(db: Session, consumer: str, event_id) -> bool:
    """Call inside the consumer's transaction: True means a redelivered event, skip it."""
    inserted = db.execute(
        text("""INSERT INTO integrations.processed_events (consumer, event_id)
                                  VALUES (:c, :e) ON CONFLICT DO NOTHING RETURNING 1"""),
        {"c": consumer, "e": event_id},
    ).first()
    return inserted is None


# ------------------------------------------------------------------ external services set up from the panel
#
# Each kind is one row: settings in clear, secrets encrypted with the installation's key (core.crypto). A change that
# turns a service on is tried first (the bucket accepts a write, the Evolution API answers with this key); a failed
# try saves nothing, so a typo never stops uploads or sign-in codes. Every process re-reads a row within 30 seconds.

CACHE_SECONDS = 30
_cache: dict[str, tuple[float, "Loaded"]] = {}
_built: dict[tuple[str, int], object] = {}


@dataclass(frozen=True)
class Loaded:
    version: int
    config: BaseModel
    secrets: dict[str, str]  # decrypted; one the current key cannot decrypt is left out (entered again)


def _kind(kind: str) -> tuple[type[BaseModel], tuple[str, ...]]:
    found = schemas.KINDS.get(kind)
    if found is None:
        raise AppError(404, "unknown_connection", kind=kind)
    return found


def _decrypt(tokens: dict) -> dict[str, str]:
    out = {}
    for name, token in tokens.items():
        try:
            out[name] = crypto.decrypt(token)
        except InvalidToken:
            log.warning("connection secret %s cannot be decrypted (was SECRET_KEY changed?)", name)
    return out


def _read(db: Session, kind: str) -> Loaded:
    model, _ = _kind(kind)
    row = db.get(Connection, kind)
    if row is None:
        return Loaded(0, model(), {})
    return Loaded(row.version, model.model_validate(row.config), _decrypt(row.secrets))


def load(db: Session, kind: str) -> Loaded:
    hit = _cache.get(kind)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    loaded = _read(db, kind)
    _cache[kind] = (time.monotonic() + CACHE_SECONDS, loaded)
    return loaded


def _on(kind: str, config: BaseModel) -> bool:
    return config.provider == "r2" if kind == "storage" else config.enabled


def _missing(kind: str, loaded: Loaded, *, always: bool = False) -> list[str]:
    """What a service that is switched on (or about to be used: always=True) still lacks."""
    if not (always or _on(kind, loaded.config)):
        return []
    c = loaded.config
    if kind == "storage":
        need = {"account_id": c.account_id, "bucket": c.bucket, "access_key_id": c.access_key_id}
    else:
        need = {"url": c.url, "instance": c.instance}
    need |= {n: loaded.secrets.get(n) for n in schemas.KINDS[kind][1]}
    return [name for name, value in need.items() if not value]


def _r2_client(loaded: Loaded):
    """The S3 client for R2; None builds the real one (tests put a fake here)."""
    return None


def _r2(loaded: Loaded) -> R2Storage:
    c = loaded.config
    return R2Storage(
        account_id=c.account_id,
        bucket=c.bucket,
        access_key_id=c.access_key_id,
        secret_access_key=loaded.secrets["secret_access_key"],
        jurisdiction=c.jurisdiction,
        client=_r2_client(loaded),
    )


def _evolution(loaded: Loaded) -> messaging.EvolutionProvider:
    c = loaded.config
    return messaging.EvolutionProvider(c.url, loaded.secrets["api_key"], c.instance)


def _try(kind: str, loaded: Loaded) -> str | None:
    """None when the service answers as it should; otherwise what went wrong, for the administrator."""
    if not _on(kind, loaded.config):
        return None
    try:
        if kind == "storage":
            _r2(loaded).check()
        else:
            _evolution(loaded).connection_state()
    except (StorageError, messaging.DeliveryError) as exc:
        return str(exc)[:300]
    return None


def _hint(value: str) -> str:
    return "…" + value[-4:]


def connection_out(db: Session, kind: str, status: dict | None = None) -> dict:
    _, secret_names = _kind(kind)
    row = db.get(Connection, kind)
    loaded = _read(db, kind)
    return {
        "kind": kind,
        "version": loaded.version,
        "config": loaded.config.model_dump(mode="json"),
        "secrets": {
            n: {"set": n in loaded.secrets, "hint": _hint(loaded.secrets[n]) if n in loaded.secrets else None}
            for n in secret_names
        },
        "updated_at": row.updated_at if row else None,
        "checked_at": row.checked_at if row else None,
        "check_ok": row.check_ok if row else None,
        "check_error": row.check_error if row else None,
        "status": status or {},
    }


def save(
    db: Session,
    kind: str,
    *,
    version: int,
    config: dict,
    secrets: dict,
    actor_user_id: int,
    r2_files: int = 0,
) -> None:
    """r2_files: how many stored files are in the R2 bucket now. While there are any, the bucket they are in cannot
    be changed or its credentials removed (they would become unreadable); the key itself may be replaced."""
    model, secret_names = _kind(kind)
    unknown = sorted(set(secrets) - set(secret_names))
    if unknown:
        raise AppError(422, "invalid_connection", detail=", ".join(unknown))
    try:
        new_config = model.model_validate(config)
    except ValidationError as exc:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise AppError(422, "invalid_connection", detail=detail) from None
    row = db.get(Connection, kind, with_for_update=True)
    if (0 if row is None else row.version) != version:
        raise AppError(409, "version_conflict")
    current = _read(db, kind)
    new_secrets = dict(current.secrets)
    for name, value in secrets.items():
        if value is None:
            new_secrets.pop(name, None)
        else:
            new_secrets[name] = value
    loaded = Loaded(version + 1, new_config, new_secrets)
    missing = _missing(kind, loaded)
    if missing:
        raise AppError(422, "connection_incomplete", fields=", ".join(missing))
    if kind == "storage" and r2_files:
        old, new = current.config, new_config
        # settings lost (a restore, a manual delete) may be entered again: only a bucket on record can be moved away
        moved = old.bucket is not None and any(
            getattr(old, f) != getattr(new, f) for f in ("account_id", "bucket", "jurisdiction")
        )
        if moved or not new_secrets.get("secret_access_key") or not new.access_key_id:
            raise AppError(409, "storage_in_use", count=r2_files)
    error = _try(kind, loaded)
    if error:
        raise AppError(422, "connection_check_failed", error=error)
    stored_config = new_config.model_dump(mode="json")
    encrypted = {}
    for name, value in new_secrets.items():
        token = row.secrets.get(name) if row is not None else None
        encrypted[name] = token if token and current.secrets.get(name) == value else crypto.encrypt(value)
    switched_on = _on(kind, new_config)
    if row is None:
        row = Connection(kind=kind, config=stored_config, secrets=encrypted, version=1)
        db.add(row)
    else:
        row.config, row.secrets, row.version = stored_config, encrypted, row.version + 1
    row.updated_by, row.updated_at = actor_user_id, func.now()
    row.checked_at, row.check_ok, row.check_error = (func.now(), True, None) if switched_on else (None, None, None)
    db.flush()
    audit.record(
        db,
        action="integration.changed",
        entity_type="integration",
        entity_id=kind,
        actor_user_id=actor_user_id,
        before=current.config.model_dump(mode="json") if current.version else None,
        after=stored_config | {"secrets_changed": sorted(n for n in secrets)},
    )
    db.commit()
    _cache.pop(kind, None)


def check(db: Session, kind: str) -> None:
    """Tries the saved settings again (the panel's "test" button) and records the answer."""
    _kind(kind)
    loaded = _read(db, kind)
    row = db.get(Connection, kind, with_for_update=True)
    if row is None:
        raise AppError(422, "connection_incomplete", fields="config")
    missing = _missing(kind, loaded)
    error = f"missing: {', '.join(missing)}" if missing else _try(kind, loaded)
    row.checked_at, row.check_ok, row.check_error = func.now(), error is None, error
    db.commit()


def _cached_build(kind: str, loaded: Loaded, build):
    key = (kind, loaded.version)
    if key not in _built:
        for old in [k for k in _built if k[0] == kind]:
            _built.pop(old)
        _built[key] = build(loaded)
    return _built[key]


def storage(db: Session, name: str | None = None) -> LocalStorage | R2Storage:
    """name=None: where a new file is written. "local" or "r2": where an existing file is read from."""
    loaded = load(db, "storage")
    name = name or loaded.config.provider
    if name == "local":
        return LocalStorage(get_settings().files_dir)
    if _missing("storage", loaded, always=True):
        raise StorageError("R2 is not set up in the control panel")
    return _cached_build("storage", loaded, _r2)


def messenger(db: Session) -> messaging.LogProvider | messaging.EvolutionProvider | messaging.PanelProvider:
    """WhatsApp as set up in the control panel; until it is switched on there, the server's configuration."""
    loaded = load(db, "whatsapp")
    if loaded.config.enabled and not _missing("whatsapp", loaded):
        return _cached_build("whatsapp", loaded, _evolution)
    return messaging.provider()
