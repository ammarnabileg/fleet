"""The channels a broadcast (ركن الإشعارات) goes out through. Each is one small class registered here:

    class Sms(Channel):
        name = "sms"
        def enabled(self, db): ...                  # its integration switched on (never switched on from here)
        def skip_reason(self, db, recipient): ...   # None, or why this driver cannot get it (no_phone, ...)
        def send(self, db, recipient, message): ... # -> Result("sent" | "failed", reason, provider_ref)
    register(Sms())

and the panel lists it, the preview counts it and the sender fans out to it. `paced` channels (WhatsApp) are sent one
message at a time at the number's shared pace by the scheduler; the others in batches.
"""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import messaging, push
from app.modules.identity import service as identity
from app.modules.integrations import service as integrations
from app.modules.notifications.models import DriverNotice

WHATSAPP_LIMIT = 4096  # characters WhatsApp takes in one message


def text_in(texts: dict | None, lang: str) -> str:
    """A broadcast's text in the driver's language; a language not written falls back to English, then Arabic."""
    texts = texts or {}
    return texts.get(lang) or texts.get("en") or texts.get("ar") or next((v for v in texts.values() if v), "")


@dataclass(frozen=True)
class Recipient:
    employee_id: int
    lang: str
    phone: str | None = None
    device_id: int | None = None  # the phone registered for push, and its token
    token: str | None = None


@dataclass(frozen=True)
class Message:
    broadcast_id: int
    public_id: str
    title: dict
    body: dict

    def title_in(self, lang: str) -> str:
        return text_in(self.title, lang)

    def body_in(self, lang: str) -> str:
        return text_in(self.body, lang)


@dataclass
class Result:
    status: str  # sent | failed | skipped
    reason: str | None = None
    provider_ref: str | None = None
    extra: dict = field(default_factory=dict)


class Channel:
    name: str = ""
    always: bool = False  # cannot be unticked (the inbox)
    paced: bool = False  # one message at a time at a shared pace (WhatsApp)
    batch: int = 500

    def enabled(self, db: Session) -> bool:
        raise NotImplementedError

    def skip_reason(self, db: Session, recipient: Recipient) -> str | None:
        return None

    def send(self, db: Session, recipient: Recipient, message: Message) -> Result:
        raise NotImplementedError


CHANNELS: dict[str, Channel] = {}


def register(channel: Channel) -> Channel:
    CHANNELS[channel.name] = channel
    return channel


def notice_key(message: Message) -> str:
    return f"broadcast:{message.public_id}"


class Inbox(Channel):
    """The app's notifications list: always. The notice keeps every language and is read in the app's own; it is
    marked pushed, as push is a channel of its own here (and may be unticked)."""

    name = "inbox"
    always = True

    def enabled(self, db: Session) -> bool:
        return True

    def send(self, db: Session, recipient: Recipient, message: Message) -> Result:
        stmt = (
            insert(DriverNotice)
            .values(
                employee_id=recipient.employee_id,
                kind="broadcast",
                params={"title": message.title, "body": message.body},
                entity_type="broadcast",
                entity_id=message.public_id,
                dedupe_key=notice_key(message),
                pushed_at=func.now(),
            )
            .on_conflict_do_nothing(
                index_elements=["employee_id", "dedupe_key"], index_where=DriverNotice.dedupe_key.is_not(None)
            )
            .returning(DriverNotice.public_id)
        )
        row = db.execute(stmt).first()
        if row is None:  # already in his inbox (a retry): the same notice
            row = db.execute(
                select(DriverNotice.public_id).where(
                    DriverNotice.employee_id == recipient.employee_id, DriverNotice.dedupe_key == notice_key(message)
                )
            ).first()
        return Result("sent", provider_ref=str(row[0]))


class Push(Channel):
    """Firebase, as set up in the integrations page: title and body in the driver's language, and data the app opens
    the notice with. Only phones that registered a token get it."""

    name = "push"

    def enabled(self, db: Session) -> bool:
        return integrations.pusher(db) is not None

    def skip_reason(self, db: Session, recipient: Recipient) -> str | None:
        return None if recipient.token else "no_token"

    def payload(self, recipient: Recipient, message: Message, notice_id: str | None) -> dict:
        return {
            "title": message.title_in(recipient.lang),
            "body": message.body_in(recipient.lang),
            "data": {
                "id": notice_id or "",
                "kind": "broadcast",
                "entity_type": "broadcast",
                "entity_id": message.public_id,
            },
        }

    def send(self, db: Session, recipient: Recipient, message: Message) -> Result:
        sender = integrations.pusher(db)
        if sender is None:
            return Result("skipped", "channel_disabled")
        if not recipient.token:
            return Result("skipped", "no_token")
        notice_id = db.scalar(
            select(DriverNotice.public_id).where(
                DriverNotice.employee_id == recipient.employee_id, DriverNotice.dedupe_key == notice_key(message)
            )
        )
        notice_id = str(notice_id) if notice_id else None
        p = self.payload(recipient, message, notice_id)
        log = {"notice_id": notice_id or message.public_id, "device_id": recipient.device_id, "purpose": "broadcast"}
        try:
            sender.send(recipient.token, title=p["title"], body=p["body"], data=p["data"])
        except push.InvalidToken:
            identity.forget_push_token(db, recipient.device_id)
            integrations.log_push(db, status="failed", error="token no longer valid", **log)
            return Result("failed", "invalid_token")
        except push.PushError as exc:
            integrations.log_push(db, status="failed", error=str(exc), **log)
            return Result("failed", "provider_error", extra={"error": str(exc)[:200]})
        integrations.log_push(db, status="accepted", **log)
        return Result("sent")


class WhatsApp(Channel):
    """WhatsApp through the integrations page's provider, one message at a time at the number's pace (the same one the
    bulk activation links keep), so the number is not flagged as spam."""

    name = "whatsapp"
    paced = True

    def enabled(self, db: Session) -> bool:
        return integrations.whatsapp_enabled(db)

    def skip_reason(self, db: Session, recipient: Recipient) -> str | None:
        return None if recipient.phone else "no_phone"

    def text(self, recipient: Recipient, message: Message) -> str:
        return f"*{message.title_in(recipient.lang)}*\n\n{message.body_in(recipient.lang)}"[:WHATSAPP_LIMIT]

    def send(self, db: Session, recipient: Recipient, message: Message) -> Result:
        if not self.enabled(db):
            return Result("skipped", "channel_disabled")
        if not recipient.phone:
            return Result("skipped", "no_phone")
        try:
            ref = integrations.messenger(db, "broadcast").send(recipient.phone, self.text(recipient, message))
        except messaging.NotOnWhatsApp:
            return Result("failed", "not_on_whatsapp")
        except messaging.DeliveryError:
            return Result("failed", "provider_error")
        except Exception:  # noqa: BLE001 (a timeout the provider let through: failed, logged by the messenger)
            return Result("failed", "provider_error")
        return Result("sent", provider_ref=ref)


register(Inbox())
register(Push())
register(WhatsApp())
