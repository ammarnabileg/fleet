import logging
import time
from dataclasses import dataclass
from datetime import timedelta

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import crypto, mailer, messaging, push
from app.core import remote_config as remote_config_api
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.db import new_session
from app.core.errors import AppError
from app.core.storage import LocalStorage, R2Storage, StorageError
from app.modules.audit import service as audit
from app.modules.integrations import schemas
from app.modules.integrations.models import Connection, EmailOutbox, MessageLog

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
    return config.provider in ("r2", "both") if kind == "storage" else config.enabled


def _missing(kind: str, loaded: Loaded, *, always: bool = False) -> list[str]:
    """What a service that is switched on (or about to be used: always=True) still lacks."""
    if not (always or _on(kind, loaded.config)):
        return []
    c = loaded.config
    if kind == "storage":
        need = {"account_id": c.account_id, "bucket": c.bucket, "access_key_id": c.access_key_id}
    elif kind == "push":
        need = {"app_id": c.app_id, "api_key": c.api_key, "sender_id": c.sender_id}
    elif kind == "email":
        need = {"host": c.host, "from_address": c.from_address, "notify_to": c.notify_to}
        if c.username:
            need["password"] = loaded.secrets.get("password")
        return [name for name, value in need.items() if not value]
    else:
        need = {"url": c.url, "instance": c.instance}
    need |= {n: loaded.secrets.get(n) for n in schemas.KINDS[kind][1]}
    return [name for name, value in need.items() if not value]


def _smtp(loaded: Loaded) -> mailer.SmtpMailer:
    c = loaded.config
    return _smtp_factory(
        c.host, c.port, c.security, c.username, loaded.secrets.get("password"), c.from_address, c.from_name or None
    )


def _smtp_factory(*args):
    """The SMTP client; tests put a fake here."""
    return mailer.SmtpMailer(*args)


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


def _fcm_transport(loaded: Loaded):
    """The HTTP transport for Google; None is the real network (tests put a fake here)."""
    return None


def _fcm(loaded: Loaded) -> push.FcmSender:
    return push.FcmSender(loaded.secrets["service_account"], transport=_fcm_transport(loaded))


def _try(kind: str, loaded: Loaded, *, even_off: bool = False) -> str | None:
    """None when the service answers as it should; otherwise what went wrong, for the administrator.
    even_off: try the saved settings of a service that is switched off too (the panel's test button)."""
    if not (even_off or _on(kind, loaded.config)):
        return None
    try:
        if kind == "storage":
            _r2(loaded).check()
        elif kind == "push":
            _fcm(loaded).check()
        elif kind == "email":
            _smtp(loaded).check()
        else:
            # the Evolution API answering is not enough: its WhatsApp session must be connected ("open"), or no
            # message goes out (a dropped session needs its QR code scanned again in Evolution)
            state = _evolution(loaded).connection_state()
            if state != "open":
                return f"whatsapp session is {state}, not open: scan the QR code again in Evolution API"
    except (StorageError, messaging.DeliveryError, push.PushError, mailer.MailError) as exc:
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
        "state": state_of(kind, loaded, row),
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
    """Tries the saved settings again (the panel's "test" button) and records the answer. WhatsApp and push are tried
    even while switched off (a test that tried nothing would read "works"); the test sends no message to anyone."""
    _kind(kind)
    loaded = _read(db, kind)
    row = db.get(Connection, kind, with_for_update=True)
    if row is None:
        raise AppError(422, "connection_incomplete", fields="config")
    even_off = kind in ("whatsapp", "push", "email")
    missing = _missing(kind, loaded, always=even_off)
    error = f"missing: {', '.join(missing)}" if missing else _try(kind, loaded, even_off=even_off)
    row.checked_at, row.check_ok, row.check_error = func.now(), error is None, error
    db.commit()
    _cache.pop(kind, None)


def record_channel_state(db: Session, state: str) -> None:
    """The scheduler's check of the WhatsApp channel (every few minutes), kept as the connection's last test while
    WhatsApp is switched on here: the panel then shows a current answer, not the one from the day it was saved."""
    row = db.get(Connection, "whatsapp")
    if row is None or not row.config.get("enabled"):
        return
    ok = state == "open"
    row.checked_at, row.check_ok = func.now(), ok
    row.check_error = None if ok else f"whatsapp session is {state}, not open"[:300]


def state_of(kind: str, loaded: Loaded, row: Connection | None) -> str:
    """The channel's readiness as the panel shows it: not_configured (settings or key missing), disabled (complete
    but switched off), untested, working (its last test passed), failed (its last test failed)."""
    if kind == "storage" and not _on(kind, loaded.config):
        return "disabled"  # R2 off: files on the server's disk
    if row is None or _missing(kind, loaded, always=True):
        return "not_configured"
    if not _on(kind, loaded.config):
        return "disabled"
    if row.checked_at is None:
        return "untested"
    return "working" if row.check_ok else "failed"


def _cached_build(kind: str, loaded: Loaded, build):
    key = (kind, loaded.version)
    if key not in _built:
        for old in [k for k in _built if k[0] == kind]:
            _built.pop(old)
        _built[key] = build(loaded)
    return _built[key]


def storage_mode(db: Session) -> str:
    """Where new files go, as chosen in the control panel: "local" (the server's disk), "r2", or "both"."""
    return load(db, "storage").config.provider


def r2_ready(db: Session) -> bool:
    """R2 is set up (whatever new files use): its files can be read, and copied back to the disk."""
    return not _missing("storage", load(db, "storage"), always=True)


def storage(db: Session, name: str) -> LocalStorage | R2Storage:
    """The disk ("local") or the R2 bucket ("r2"), to write or read a file's copy there."""
    if name == "local":
        return LocalStorage(get_settings().files_dir)
    loaded = load(db, "storage")
    if _missing("storage", loaded, always=True):
        raise StorageError("R2 is not set up in the control panel")
    return _cached_build("storage", loaded, _r2)


def messenger(db: Session, purpose: str | None = None) -> "Recorded":
    """WhatsApp as set up in the control panel; until it is switched on there, the server's configuration. Every send
    is kept in the message log (purpose: why it is sent, e.g. "otp"), whatever the caller does with its transaction."""
    loaded = load(db, "whatsapp")
    if loaded.config.enabled and not _missing("whatsapp", loaded):
        return Recorded(_cached_build("whatsapp", loaded, _evolution), purpose)
    return Recorded(messaging.provider(), purpose)


def _provider_name(provider) -> str:
    if isinstance(provider, messaging.EvolutionProvider):
        return "evolution"
    if isinstance(provider, messaging.LogProvider):
        return "log"
    if isinstance(provider, messaging.PanelProvider):
        return "none"
    return type(provider).__name__.lower()[:30]


def _masked(to: str | None) -> str | None:
    digits = "".join(ch for ch in (to or "") if ch.isdigit())
    return "…" + digits[-4:] if digits else None


class Recorded:
    """A messaging provider whose sends are written to the message log, in a session of their own: callers roll back
    on a failed send, and the failure is exactly what the log must keep. The text is never written."""

    def __init__(self, provider, purpose: str | None) -> None:
        self.provider = provider
        self.purpose = purpose

    def connection_state(self) -> str:
        return self.provider.connection_state()

    def send(self, to: str, text: str) -> str | None:
        """The provider's message id, when it gives one."""
        try:
            ref = self.provider.send(to, text)
        except messaging.DeliveryError as exc:
            reason = "not_on_whatsapp" if isinstance(exc, messaging.NotOnWhatsApp) else str(exc)
            _log_message("whatsapp", _provider_name(self.provider), self.purpose, to, "failed", error=reason)
            raise
        except Exception as exc:  # a timeout or any other transport error the provider let through: failed too
            name = _provider_name(self.provider)
            _log_message("whatsapp", name, self.purpose, to, "failed", error=type(exc).__name__)
            raise
        _log_message("whatsapp", _provider_name(self.provider), self.purpose, to, "accepted", provider_ref=ref)
        return ref if isinstance(ref, str) else None


def whatsapp_enabled(db: Session) -> bool:
    """WhatsApp really goes out: switched on in the control panel, or the server is set up with Evolution itself. The
    development log and a panel not switched on yet send nothing, so a broadcast skips the channel."""
    loaded = load(db, "whatsapp")
    if loaded.config.enabled and not _missing("whatsapp", loaded):
        return True
    return get_settings().messaging_provider == "whatsapp"


def _log_message(channel, provider, purpose, to, status, *, error=None, provider_ref=None) -> None:
    try:
        with new_session() as s:
            s.add(
                MessageLog(
                    channel=channel,
                    provider=provider,
                    purpose=purpose,
                    recipient=_masked(to),
                    status=status,
                    error=(error or None) and str(error)[:300],
                    provider_ref=provider_ref if isinstance(provider_ref, str) else None,
                )
            )
            s.commit()
    except Exception:  # noqa: BLE001 (the log must never stop a message or its caller)
        log.exception("message log not written")


def log_push(
    db: Session, *, status: str, notice_id: str, device_id: int, error: str | None = None, purpose: str = "notice"
) -> None:
    """A push to a driver's phone (in the caller's transaction): accepted by Firebase, or failed and why. A notice
    tried again counts its attempts."""
    tried = select(func.count()).where(MessageLog.channel == "push", MessageLog.ref == notice_id)
    attempt = 1 + (db.scalar(tried) or 0)
    db.add(
        MessageLog(
            channel="push",
            provider="fcm",
            purpose=purpose,
            recipient=f"device {device_id}",
            status=status,
            error=error and error[:300],
            ref=notice_id,
            attempt=attempt,
        )
    )


MESSAGE_LOG_DAYS = 90


def messages_summary(db: Session, channel: str, *, days: int = 7, recent: int = 20) -> dict:
    """What the integrations page shows under a channel: messages accepted and failed lately, the last of each, and
    the latest messages one by one (no text, the recipient's last digits only)."""
    since = utcnow() - timedelta(days=days)
    counts = dict(
        db.execute(
            select(MessageLog.status, func.count())
            .where(MessageLog.channel == channel, MessageLog.created_at >= since)
            .group_by(MessageLog.status)
        ).all()
    )
    last = {
        status: db.scalar(
            select(MessageLog)
            .where(MessageLog.channel == channel, MessageLog.status == status)
            .order_by(MessageLog.id.desc())
            .limit(1)
        )
        for status in ("accepted", "failed")
    }
    rows = db.scalars(
        select(MessageLog).where(MessageLog.channel == channel).order_by(MessageLog.id.desc()).limit(recent)
    ).all()
    return {
        "days": days,
        "accepted": counts.get("accepted", 0),
        "failed": counts.get("failed", 0),
        "last_accepted_at": last["accepted"].created_at if last["accepted"] else None,
        "last_failed_at": last["failed"].created_at if last["failed"] else None,
        "last_error": last["failed"].error if last["failed"] else None,
        "recent": [
            {
                "at": m.created_at,
                "provider": m.provider,
                "purpose": m.purpose,
                "recipient": m.recipient,
                "status": m.status,
                "error": m.error,
                "attempt": m.attempt,
                "ref": m.ref,
            }
            for m in rows
        ],
    }


def purge_message_log(db: Session) -> int:
    """Daily: messages older than MESSAGE_LOG_DAYS are deleted."""
    n = db.execute(
        text("DELETE FROM integrations.message_log WHERE created_at < now() - make_interval(days => :d)"),
        {"d": MESSAGE_LOG_DAYS},
    ).rowcount
    db.commit()
    return n


def pusher(db: Session) -> push.FcmSender | None:
    """FCM as set up in the control panel; None until it is switched on there (notices then wait in the app)."""
    loaded = load(db, "push")
    if not loaded.config.enabled or _missing("push", loaded):
        return None
    return _cached_build("push", loaded, _fcm)


def push_client(db: Session) -> dict | None:
    """What the app needs to register with Firebase (public values), once push is switched on."""
    loaded = load(db, "push")
    if not loaded.config.enabled or _missing("push", loaded):
        return None
    c = loaded.config
    try:
        project = push.parse_service_account(loaded.secrets["service_account"])["project_id"]
    except push.PushError:
        return None
    return {"project_id": project, "app_id": c.app_id, "api_key": c.api_key, "sender_id": c.sender_id}


def remote_config(db: Session) -> remote_config_api.RemoteConfigClient | None:
    """Firebase Remote Config with push's service account, once push is switched on in the control panel (the app
    starts Firebase only then, so a value written before would reach no phone)."""
    loaded = load(db, "push")
    if not loaded.config.enabled or _missing("push", loaded):
        return None
    return _cached_build(
        "remote_config",
        loaded,
        lambda x: remote_config_api.RemoteConfigClient(x.secrets["service_account"], transport=_fcm_transport(x)),
    )


# ------------------------------------------------------------------ email (the "email" connection)

ERROR_MAIL_EVERY = timedelta(minutes=30)
MAIL_TRIES = 5


def email_ready(db: Session) -> bool:
    loaded = load(db, "email")
    return bool(loaded.config.enabled) and not _missing("email", loaded, always=True)


def queue_email(
    db: Session,
    kind: str,
    subject: str,
    body: str,
    *,
    reply_to: str | None = None,
    dedupe_key: str | None = None,
) -> bool:
    """Adds an email for the office's addresses to the caller's transaction; the background job sends it. Nothing is
    queued while email is off, nor an error alert when those are off, nor the same error again within 30 minutes."""
    if not email_ready(db):
        return False
    if kind == "error":
        if not load(db, "email").config.error_alerts:
            return False
        if dedupe_key and db.scalar(
            select(EmailOutbox.id)
            .where(EmailOutbox.dedupe_key == dedupe_key, EmailOutbox.created_at > utcnow() - ERROR_MAIL_EVERY)
            .limit(1)
        ):
            return False
    db.add(EmailOutbox(kind=kind, subject=subject[:300], body=body[:20000], reply_to=reply_to, dedupe_key=dedupe_key))
    return True


def send_queued_emails(db: Session, limit: int = 20) -> int:
    """Sends what waits (oldest first) to the addresses set now; a refusal is kept with its reason and tried again
    on the next run, up to five times."""
    if not email_ready(db):
        return 0
    loaded = load(db, "email")
    rows = db.scalars(
        select(EmailOutbox)
        .where(EmailOutbox.sent_at.is_(None), EmailOutbox.attempts < MAIL_TRIES)
        .order_by(EmailOutbox.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    sent = 0
    client = _smtp(loaded) if rows else None
    for row in rows:
        row.attempts += 1
        try:
            client.send(list(loaded.config.notify_to), row.subject, row.body, reply_to=row.reply_to)
            row.sent_at, row.last_error = utcnow(), None
            sent += 1
        except mailer.MailError as exc:
            row.last_error = str(exc)[:300]
        db.commit()
    return sent


def report_error(where: str, exc: BaseException, detail: str = "") -> None:
    """A serious error (a page that failed, a background job that failed), emailed to the office in a session of its
    own: whatever the failing code left in its transaction, the alert is still queued. Never raises."""
    import traceback

    try:
        kind_ = exc.__class__.__name__
        origin = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
        key = f"error:{where}:{kind_}:{origin.filename}:{origin.lineno}" if origin else f"error:{where}:{kind_}"
        settings = get_settings()
        body = (
            f"A serious error happened on {settings.public_url}\n\n"
            f"Where: {where}\n{detail}\nError: {kind_}: {str(exc)[:500]}\n"
            f"Time (UTC): {utcnow():%Y-%m-%d %H:%M:%S}\n\n"
            + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:]
            + "\n\nThe same error is not emailed again for 30 minutes. Details are in the server logs."
        )
        with new_session() as db:
            if queue_email(db, "error", f"[Error] {kind_} in {where}"[:200], body, dedupe_key=key[:500]):
                db.commit()
    except Exception:  # noqa: BLE001 - reporting must never make the failure worse
        logging.getLogger("fleet.errors").exception("could not queue the error email")
