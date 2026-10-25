"""The company's public site on the main domain: its content (the "site" settings section, edited in the panel), and
the messages its contact form sends. Everything the public reads goes through public_content(): the section as
saved, plus whether an app release can be downloaded."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import context
from app.core.clock import utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.integrations import service as integrations
from app.modules.notifications import service as notifications
from app.modules.org import service
from app.modules.org.models import SiteMessage

STATUSES = ("new", "read", "done")


def public_content(db: Session, *, download: bool) -> dict:
    site = service.get_section(db, "site")
    if not site.enabled:
        raise AppError(404, "site_off")
    out = site.model_dump(mode="json")
    out["download"] = bool(site.show_download and download)
    return out


def logo(db: Session, sha256: str) -> files.FileInfo:
    """The logo set now, and only that one: the public reads no other file."""
    site = service.get_section(db, "site")
    if not site.enabled or site.logo is None or site.logo != sha256:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def send_message(db: Session, *, name: str, phone: str | None, email: str | None, message: str, lang: str | None):
    site = service.get_section(db, "site")
    if not (site.enabled and site.show_contact_form):
        raise AppError(404, "site_off")
    row = SiteMessage(
        name=name, phone=phone or None, email=email or None, message=message, lang=lang, ip=context.client_ip.get()
    )
    db.add(row)
    db.flush()
    notifications.raise_alert(
        db,
        "site_message",
        company_id=None,
        entity_type="site_message",
        entity_id=row.public_id,
        params={"name": name},
        dedupe_key=f"site_message:{row.public_id}",
    )
    integrations.queue_email(
        db,
        "contact",
        f"رسالة جديدة من الموقع: {name}",
        f"الاسم: {name}\nالتليفون: {phone or '-'}\nالإيميل: {email or '-'}\n\n{message}\n\n"
        "اقرأها وعلّمها من الداشبورد: الإدارة ← الموقع التعريفي ← رسائل تواصل معنا.",
        reply_to=email or None,
    )
    db.commit()


def _out(m: SiteMessage) -> dict:
    return {
        "id": str(m.public_id),
        "name": m.name,
        "phone": m.phone,
        "email": m.email,
        "message": m.message,
        "lang": m.lang,
        "status": m.status,
        "created_at": m.created_at,
        "handled_at": m.handled_at,
    }


def list_messages(db: Session, status: str | None = None, limit: int = 200) -> list[dict]:
    q = select(SiteMessage).order_by(SiteMessage.created_at.desc()).limit(limit)
    if status:
        q = q.where(SiteMessage.status == status)
    return [_out(m) for m in db.scalars(q)]


def counts(db: Session) -> dict[str, int]:
    rows = dict(db.execute(select(SiteMessage.status, func.count()).group_by(SiteMessage.status)).all())
    return {s: rows.get(s, 0) for s in STATUSES}


def set_status(db: Session, public_id: uuid.UUID, status: str, *, actor_user_id: int) -> dict:
    m = db.scalar(select(SiteMessage).where(SiteMessage.public_id == public_id).with_for_update())
    if m is None:
        raise AppError(404, "site_message_not_found")
    if m.status != status:
        before = m.status
        m.status, m.handled_by, m.handled_at = status, actor_user_id, utcnow()
        audit.record(
            db,
            action="site_message.status",
            entity_type="site_message",
            entity_id=m.public_id,
            actor_user_id=actor_user_id,
            before={"status": before},
            after={"status": status},
        )
        if status == "done":
            notifications.resolve(db, f"site_message:{m.public_id}")
    db.commit()
    return _out(m)
