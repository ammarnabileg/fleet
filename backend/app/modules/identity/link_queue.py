"""Bulk activation links: queued, then sent one at a time over WhatsApp, spaced out (settings: interval, daily limit,
hours of the day in Kuwait time). An unofficial WhatsApp number that sends hundreds of links at once is the fastest
way to get it banned; this keeps the pace of a person.

The queue lives in the database: a restart loses nothing. If WhatsApp is down the message stays queued and is
retried (3 attempts); a number without WhatsApp fails at once with its reason.
"""

import math
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, utcnow
from app.core.errors import AppError
from app.modules.identity import devices
from app.modules.identity.models import Device, LinkQueueItem
from app.modules.org import service as org
from app.modules.people import service as people

MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=10)
RETRY_LATER = {"message_not_delivered"}  # the channel is down: try again, it is not the driver's fault


def _bound(db: Session, employee_ids: list[int]) -> set[int]:
    if not employee_ids:
        return set()
    q = select(Device.employee_id).where(Device.employee_id.in_(employee_ids), Device.revoked_at.is_(None))
    return set(db.scalars(q))


def queue(db: Session, drivers: list[people.EmployeeRef], *, onboarding_for: set[int], actor_user_id: int) -> dict:
    """`onboarding_for`: the drivers whose link opens the self-registration."""
    queued, skipped = 0, []
    for d in drivers:
        if not d.can_use_app:
            skipped.append({"id": str(d.public_id), "reason": "driver_app_not_active"})
            continue
        stmt = (
            insert(LinkQueueItem)
            .values(
                employee_id=d.id,
                company_id=d.company_id,
                onboarding=d.id in onboarding_for,
                requested_by=actor_user_id,
            )
            .on_conflict_do_nothing(index_elements=["employee_id"], index_where=LinkQueueItem.status == "queued")
        )
        if db.execute(stmt.returning(LinkQueueItem.id)).first():
            queued += 1
        else:
            skipped.append({"id": str(d.public_id), "reason": "already_queued"})
    db.commit()
    return {"queued": queued, "skipped": skipped}


def unbound_drivers(db: Session, **scope) -> list[people.EmployeeRef]:
    """Drivers with app access and no phone bound yet: the first wave of links."""
    drivers = people.app_drivers(db, **scope)
    bound = _bound(db, [d.id for d in drivers])
    return [d for d in drivers if d.id not in bound]


def _day_start(now: datetime) -> datetime:
    local = now.astimezone(KUWAIT)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def summary(db: Session, *, all_companies: bool, company_ids) -> dict:
    settings = org.get_section(db, "messaging")
    now = utcnow()
    scoped = (lambda q: q) if all_companies else (lambda q: q.where(LinkQueueItem.company_id.in_(list(company_ids))))
    waiting = db.scalar(scoped(select(func.count()).select_from(LinkQueueItem).where(LinkQueueItem.status == "queued")))
    sent_today = db.scalar(
        select(func.count())
        .select_from(LinkQueueItem)
        .where(LinkQueueItem.status == "sent", LinkQueueItem.sent_at >= _day_start(now))
    )
    rows = db.execute(scoped(select(LinkQueueItem).order_by(LinkQueueItem.id.desc()).limit(200))).scalars().all()
    names = people.names(db, [r.employee_id for r in rows])
    per_day = min(
        settings.bulk_daily_limit,
        (settings.send_until_hour - settings.send_from_hour) * 3600 // settings.bulk_interval_seconds,
    )
    return {
        "waiting": waiting,
        "sent_today": sent_today,  # across all companies: the WhatsApp number is shared
        "daily_limit": settings.bulk_daily_limit,
        "estimated_days": math.ceil(waiting / per_day) if waiting and per_day else 0,
        "items": [
            {
                "id": str(r.public_id),
                "driver": names.get(r.employee_id),
                "status": r.status,
                "onboarding": r.onboarding,
                "requested_at": r.requested_at,
                "sent_at": r.sent_at,
                "error": r.error,
                "attempts": r.attempts,
            }
            for r in rows
        ],
    }


def cancel_waiting(db: Session, *, actor_user_id: int, all_companies: bool, company_ids) -> int:
    q = update(LinkQueueItem).where(LinkQueueItem.status == "queued")
    if not all_companies:
        q = q.where(LinkQueueItem.company_id.in_(list(company_ids)))
    count = db.execute(q.values(status="cancelled", error="cancelled")).rowcount
    db.commit()
    return count


def send_next(db: Session, now: datetime | None = None) -> str:
    """Called every few seconds by the scheduler; sends at most one message when the pace allows it."""
    settings = org.get_section(db, "messaging")
    now = now or utcnow()
    if not settings.send_from_hour <= now.astimezone(KUWAIT).hour < settings.send_until_hour:
        return "outside_hours"
    last = db.scalar(select(func.max(LinkQueueItem.last_attempt_at)))
    if last and now - last < timedelta(seconds=settings.bulk_interval_seconds):
        return "too_soon"
    sent_today = db.scalar(
        select(func.count())
        .select_from(LinkQueueItem)
        .where(LinkQueueItem.status == "sent", LinkQueueItem.sent_at >= _day_start(now))
    )
    if sent_today >= settings.bulk_daily_limit:
        return "daily_limit"
    item = db.scalar(
        select(LinkQueueItem)
        .where(
            LinkQueueItem.status == "queued",
            (LinkQueueItem.last_attempt_at.is_(None)) | (LinkQueueItem.last_attempt_at < now - RETRY_AFTER),
        )
        .order_by(LinkQueueItem.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if item is None:
        return "empty"
    item_id = item.id
    driver = people.ref(db, item.employee_id)
    item.attempts += 1
    item.last_attempt_at = now
    db.commit()  # the attempt counts even if the process dies while sending
    error = None
    try:
        devices.create_activation_link(
            db, driver, channel="whatsapp", actor_user_id=item.requested_by, onboarding=item.onboarding
        )
    except AppError as exc:
        db.rollback()
        error = exc.code
    item = db.get(LinkQueueItem, item_id)
    if error is None:
        item.status, item.sent_at, item.error = "sent", now, None
    elif error in RETRY_LATER and item.attempts < MAX_ATTEMPTS:
        item.error = error  # stays queued: retried after RETRY_AFTER
    else:
        item.status, item.error = "failed", error
    db.commit()
    return "sent" if error is None else error
