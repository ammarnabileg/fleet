"""Broadcasts (ركن الإشعارات): one message from the office to all drivers or a chosen group, through every channel that
is switched on (see channels.py). Sending one:

1. the audience is resolved within the sender's companies and one delivery row is written per recipient and channel
   (unique: a retry never sends twice), queued, or skipped at once with its reason (no_token, no_phone,
   channel_disabled);
2. the inbox rows are written in the same request (the drivers see it at once);
3. the scheduler (every few seconds) sends the push rows in batches and the WhatsApp rows one at a time at the
   number's pace, starts the scheduled broadcasts that are due, and marks a broadcast sent once nothing waits.

A row is claimed (committed) before an outside send: a process that dies mid-send leaves it claimed, and it is marked
failed ("interrupted") rather than sent again. Failed rows may be sent again from the panel.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.fleet import service as fleet
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.notifications import channels as ch
from app.modules.notifications.models import Broadcast, BroadcastDelivery
from app.modules.org import service as org
from app.modules.people import service as people

LANGS = ("ar", "en", "fr", "sw", "hi", "fil")
REQUIRED_LANGS = ("ar", "en")
AUDIENCES = ("all", "company", "platform", "on_duty", "selected")
INTERRUPTED_AFTER = timedelta(minutes=15)
STATS = ("queued", "sent", "failed", "skipped")


# ------------------------------------------------------------------ audience


def _audience(db: Session, audience: dict, *, all_companies: bool, company_ids) -> list[people.EmployeeRef]:
    """The drivers the broadcast goes to: not departed, within the sender's companies."""
    kind = audience.get("kind")
    drivers = [
        d for d in people.all_drivers(db, all_companies=all_companies, company_ids=company_ids) if not d.is_terminal
    ]
    if kind == "all":
        return drivers
    if kind == "company":
        wanted = set(audience.get("company_ids") or [])
        return [d for d in drivers if d.company_id in wanted]
    if kind == "platform":
        wanted = set(audience.get("platform_ids") or [])
        return [d for d in drivers if d.platform_id in wanted]
    if kind == "on_duty":
        custodies = fleet.open_custodies(db)
        working = fleet.on_duty_now(db, [c.id for c in custodies])
        on = {c.driver_id for c in custodies if c.id in working}
        return [d for d in drivers if d.id in on]
    if kind == "selected":
        wanted = {str(x) for x in audience.get("employee_ids") or []}
        return [d for d in drivers if str(d.public_id) in wanted]
    raise AppError(422, "invalid_audience")


def _check_audience(audience: dict) -> dict:
    kind = audience.get("kind")
    if kind not in AUDIENCES:
        raise AppError(422, "invalid_audience")
    key = {"company": "company_ids", "platform": "platform_ids", "selected": "employee_ids"}.get(kind)
    out = {"kind": kind}
    if key:
        values = audience.get(key) or []
        if not values:
            raise AppError(422, "invalid_audience")
        out[key] = [str(v) if key == "employee_ids" else int(v) for v in values]
    return out


def _recipients(db: Session, drivers: list[people.EmployeeRef]) -> list[ch.Recipient]:
    ids = [d.id for d in drivers]
    targets = identity.push_targets(db, ids)
    chosen = identity.preferred_languages(db, ids)
    active = {lang.code for lang in i18n.list_languages(db)}
    default = i18n.default_language(db).code
    out = []
    for d in drivers:
        target = targets.get(d.id)
        lang = chosen.get(d.id) or (target[2] if target else None)
        lang = lang if lang in active else default
        out.append(
            ch.Recipient(
                d.id, lang, d.phone, device_id=target[0] if target else None, token=target[1] if target else None
            )
        )
    return out


def _channels(requested) -> list[str]:
    unknown = set(requested) - set(ch.CHANNELS)
    if unknown:
        raise AppError(422, "unknown_channel", channel=", ".join(sorted(unknown)))
    always = [c.name for c in ch.CHANNELS.values() if c.always]
    return [name for name in ch.CHANNELS if name in always or name in requested]


def _plan(db: Session, recipients: list[ch.Recipient], channels: list[str]) -> dict[str, dict]:
    """Per channel: the recipients it will reach, and the others with their reason."""
    plan = {}
    for name in channels:
        channel = ch.CHANNELS[name]
        on = channel.enabled(db)
        rows = {}
        for r in recipients:
            rows[r.employee_id] = (r, "channel_disabled" if not on else channel.skip_reason(db, r))
        plan[name] = rows
    return plan


def channel_states(db: Session) -> list[dict]:
    return [
        {"name": c.name, "enabled": c.enabled(db), "always": c.always, "paced": c.paced} for c in ch.CHANNELS.values()
    ]


def _pace(db: Session) -> dict:
    s = org.get_section(db, "messaging")
    return {
        "interval_seconds": s.bulk_interval_seconds,
        "daily_limit": s.bulk_daily_limit,
        "from_hour": s.send_from_hour,
        "until_hour": s.send_until_hour,
    }


def preview(db: Session, *, audience: dict, channels, all_companies: bool, company_ids) -> dict:
    """How many drivers each channel will reach before sending (the confirmation shows it), and why not the others."""
    audience = _check_audience(audience)
    names = _channels(channels)
    recipients = _recipients(db, _audience(db, audience, all_companies=all_companies, company_ids=company_ids))
    plan = _plan(db, recipients, names)
    out = {}
    for name, rows in plan.items():
        skipped: dict[str, int] = {}
        for _, reason in rows.values():
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
        out[name] = {"will": sum(1 for _, reason in rows.values() if not reason), "skipped": skipped}
    reached_elsewhere = {
        e for name, rows in plan.items() if name != "inbox" for e, (_, reason) in rows.items() if not reason
    }
    return {
        "recipients": len(recipients),
        "channels": out,
        "inbox_only": len(recipients) - len(reached_elsewhere),
        "states": channel_states(db),
        "pace": _pace(db),
    }


# ------------------------------------------------------------------ compose, send, cancel


def _texts(values: dict, field: str) -> dict:
    out = {}
    for lang, text in (values or {}).items():
        if lang not in LANGS:
            raise AppError(422, "invalid_broadcast", detail=f"{field}.{lang}")
        text = (text or "").strip()
        if text:
            out[lang] = text
    missing = [lang for lang in REQUIRED_LANGS if lang not in out]
    if missing:
        raise AppError(422, "broadcast_text_required", field=field, langs=", ".join(missing))
    return out


def _get(db: Session, public_id, *, lock: bool = False) -> Broadcast:
    q = select(Broadcast).where(Broadcast.public_id == public_id)
    if lock:
        q = q.with_for_update()
    b = db.scalar(q)
    if b is None:
        raise AppError(404, "broadcast_not_found")
    return b


def _scope_of(b: Broadcast) -> dict:
    return b.audience.get("_scope") or {"all_companies": True, "company_ids": []}


def create(
    db: Session,
    *,
    title: dict,
    body: dict,
    audience: dict,
    channels,
    scheduled_at: datetime | None,
    send: bool,
    actor_user_id: int,
    all_companies: bool,
    company_ids,
) -> dict:
    """send=False keeps a draft; with scheduled_at the scheduler sends it then; otherwise it goes now."""
    title, body = _texts(title, "title"), _texts(body, "body")
    audience = _check_audience(audience)
    names = _channels(channels)
    if scheduled_at is not None and scheduled_at <= utcnow():
        scheduled_at = None  # a time already past: now
    b = Broadcast(
        title=title,
        body=body,
        audience=audience | {"_scope": {"all_companies": all_companies, "company_ids": sorted(company_ids)}},
        channels=names,
        status="draft",
        scheduled_at=scheduled_at,
        created_by=actor_user_id,
    )
    db.add(b)
    db.flush()
    audit.record(
        db,
        action="broadcast.created",
        entity_type="broadcast",
        entity_id=str(b.public_id),
        actor_user_id=actor_user_id,
        after={
            "title": title,
            "audience": audience,
            "channels": names,
            "scheduled_at": scheduled_at and str(scheduled_at),
        },
    )
    if send:
        _release(db, b, actor_user_id)
    db.commit()
    return detail(db, b.public_id)


def _release(db: Session, b: Broadcast, actor_user_id: int | None) -> None:
    if b.scheduled_at is not None and b.scheduled_at > utcnow():
        b.status = "scheduled"
        audit.record(
            db,
            action="broadcast.scheduled",
            entity_type="broadcast",
            entity_id=str(b.public_id),
            actor_user_id=actor_user_id,
            after={"scheduled_at": str(b.scheduled_at)},
        )
        return
    _start(db, b, actor_user_id)


def send_draft(db: Session, public_id, *, actor_user_id: int) -> dict:
    b = _get(db, public_id, lock=True)
    if b.status != "draft":
        raise AppError(409, "broadcast_not_draft")
    _release(db, b, actor_user_id)
    db.commit()
    return detail(db, b.public_id)


def _start(db: Session, b: Broadcast, actor_user_id: int | None) -> None:
    """Fans the broadcast out: one row per recipient and channel (queued or skipped), then the inbox at once."""
    recipients = _recipients(db, _audience(db, b.audience, **_scope_of(b)))
    plan = _plan(db, recipients, list(b.channels))
    rows = [
        {
            "broadcast_id": b.id,
            "employee_id": r.employee_id,
            "channel": name,
            "status": "skipped" if reason else "queued",
            "reason": reason,
            "lang": r.lang,
        }
        for name, by in plan.items()
        for r, reason in by.values()
    ]
    for i in range(0, len(rows), 1000):
        db.execute(insert(BroadcastDelivery).values(rows[i : i + 1000]).on_conflict_do_nothing())
    b.status, b.started_at, b.recipients = "sending", func.now(), len(recipients)
    db.flush()
    audit.record(
        db,
        action="broadcast.sent",
        entity_type="broadcast",
        entity_id=str(b.public_id),
        actor_user_id=actor_user_id,
        after={"recipients": len(recipients), "channels": list(b.channels)},
    )
    _send_batch(db, b, "inbox", limit=None)
    _finish_if_done(db, b)


def cancel(db: Session, public_id, *, actor_user_id: int) -> dict:
    """A draft or a scheduled broadcast, or what still waits of one being sent (WhatsApp goes at the number's pace)."""
    b = _get(db, public_id, lock=True)
    if b.status not in ("draft", "scheduled", "sending"):
        raise AppError(409, "broadcast_not_cancellable")
    left = db.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.broadcast_id == b.id,
            BroadcastDelivery.status == "queued",
            BroadcastDelivery.claimed_at.is_(None),
        )
        .values(status="skipped", reason="cancelled", updated_at=func.now())
    ).rowcount
    b.status, b.cancelled_at, b.cancelled_by = "cancelled", func.now(), actor_user_id
    audit.record(
        db,
        action="broadcast.cancelled",
        entity_type="broadcast",
        entity_id=str(b.public_id),
        actor_user_id=actor_user_id,
        after={"unsent": left},
    )
    db.commit()
    return detail(db, b.public_id)


def resend_failed(db: Session, public_id, *, actor_user_id: int, channel: str | None = None) -> dict:
    b = _get(db, public_id, lock=True)
    if b.status not in ("sending", "sent"):
        raise AppError(409, "broadcast_not_sent")
    q = update(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == b.id, BroadcastDelivery.status == "failed")
    if channel:
        q = q.where(BroadcastDelivery.channel == channel)
    n = db.execute(q.values(status="queued", reason=None, claimed_at=None, updated_at=func.now())).rowcount
    if n:
        b.status, b.sent_at = "sending", None
    audit.record(
        db,
        action="broadcast.resent",
        entity_type="broadcast",
        entity_id=str(b.public_id),
        actor_user_id=actor_user_id,
        after={"requeued": n, "channel": channel},
    )
    db.commit()
    return detail(db, b.public_id) | {"requeued": n}


# ------------------------------------------------------------------ sending (the scheduler)


def _message(b: Broadcast) -> ch.Message:
    return ch.Message(b.id, str(b.public_id), b.title, b.body)


def _recipient_of(db: Session, d: BroadcastDelivery, refs: dict, targets: dict) -> ch.Recipient:
    ref = refs.get(d.employee_id)
    target = targets.get(d.employee_id)
    return ch.Recipient(
        d.employee_id,
        d.lang or "ar",
        ref.phone if ref else None,
        device_id=target[0] if target else None,
        token=target[1] if target else None,
    )


def _apply(d: BroadcastDelivery, result: ch.Result) -> None:
    d.status, d.reason, d.updated_at = result.status, result.reason, func.now()
    d.provider_ref = result.provider_ref or d.provider_ref
    if result.status == "sent":
        d.sent_at = func.now()


def _send_batch(db: Session, b: Broadcast, name: str, *, limit: int | None) -> int:
    """Sends the queued rows of one channel (in the caller's transaction for the inbox; an outside channel claims its
    rows first, committed, so a crash never sends them twice)."""
    channel = ch.CHANNELS[name]
    q = (
        select(BroadcastDelivery)
        .where(
            BroadcastDelivery.broadcast_id == b.id,
            BroadcastDelivery.channel == name,
            BroadcastDelivery.status == "queued",
            BroadcastDelivery.claimed_at.is_(None),
        )
        .order_by(BroadcastDelivery.id)
        .with_for_update(skip_locked=True)
    )
    if limit:
        q = q.limit(limit)
    rows = list(db.scalars(q))
    if not rows:
        return 0
    outside = name != "inbox"
    if outside:
        for d in rows:
            d.attempts += 1
            d.claimed_at = func.now()
        db.commit()
    ids = [d.employee_id for d in rows]
    refs = {i: people.ref(db, i) for i in ids} if name == "whatsapp" else {}
    targets = identity.push_targets(db, ids) if name == "push" else {}
    message = _message(b)
    for d in rows:
        if not outside:
            d.attempts += 1
        _apply(d, channel.send(db, _recipient_of(db, d, refs, targets), message))
    if outside:
        db.commit()
    return len(rows)


def _finish_if_done(db: Session, b: Broadcast) -> None:
    waiting = db.scalar(
        select(func.count()).where(BroadcastDelivery.broadcast_id == b.id, BroadcastDelivery.status == "queued")
    )
    if not waiting and b.status == "sending":
        b.status, b.sent_at = "sent", func.now()


def _mark_interrupted(db: Session) -> int:
    n = db.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.status == "queued",
            BroadcastDelivery.claimed_at.is_not(None),
            BroadcastDelivery.claimed_at < utcnow() - INTERRUPTED_AFTER,
        )
        .values(status="failed", reason="interrupted", updated_at=func.now())
    ).rowcount
    db.commit()
    return n


def send_whatsapp_next(db: Session, now: datetime | None = None) -> str:
    """At most one WhatsApp message, when the number's shared pace allows it (hours, interval, daily limit)."""
    now = now or utcnow()
    waiting = db.scalar(
        select(BroadcastDelivery.id)
        .join(Broadcast, Broadcast.id == BroadcastDelivery.broadcast_id)
        .where(
            Broadcast.status == "sending",
            BroadcastDelivery.channel == "whatsapp",
            BroadcastDelivery.status == "queued",
            BroadcastDelivery.claimed_at.is_(None),
        )
        .order_by(BroadcastDelivery.id)
        .limit(1)
    )
    if waiting is None:
        return "empty"
    blocked = identity.whatsapp_pace(db, now)
    if blocked:
        return blocked
    d = db.scalar(
        select(BroadcastDelivery)
        .where(BroadcastDelivery.id == waiting, BroadcastDelivery.claimed_at.is_(None))
        .with_for_update(skip_locked=True)
    )
    if d is None:
        return "taken"
    b = db.get(Broadcast, d.broadcast_id)
    d.attempts += 1
    d.claimed_at = now
    db.commit()  # claimed: counts for the pace, and is never sent twice
    recipient = _recipient_of(db, d, {d.employee_id: people.ref(db, d.employee_id)}, {})
    result = ch.CHANNELS["whatsapp"].send(db, recipient, _message(b))
    _apply(d, result)
    _finish_if_done(db, b)
    db.commit()
    return result.status


def run(db: Session, now: datetime | None = None) -> dict:
    """The scheduler's pass: due scheduled broadcasts started, push batches sent, one WhatsApp message at the pace,
    finished broadcasts marked sent."""
    now = now or utcnow()
    started = 0
    for b in db.scalars(
        select(Broadcast)
        .where(Broadcast.status == "scheduled", Broadcast.scheduled_at <= now)
        .order_by(Broadcast.scheduled_at)
        .with_for_update(skip_locked=True)
    ).all():
        _start(db, b, None)
        db.commit()
        started += 1
    _mark_interrupted(db)
    pushed = 0
    for b in db.scalars(select(Broadcast).where(Broadcast.status == "sending").order_by(Broadcast.id)).all():
        for name, channel in ch.CHANNELS.items():
            if name in b.channels and not channel.paced:
                pushed += _send_batch(db, b, name, limit=channel.batch)
        _finish_if_done(db, b)
        db.commit()
    whatsapp = send_whatsapp_next(db, now)
    return {"started": started, "sent": pushed, "whatsapp": whatsapp}


def bulk_whatsapp_usage(db: Session, since: datetime) -> tuple[datetime | None, int]:
    """For the shared WhatsApp pace: the last broadcast message tried, and how many went out since."""
    last = db.scalar(select(func.max(BroadcastDelivery.claimed_at)).where(BroadcastDelivery.channel == "whatsapp"))
    sent = db.scalar(
        select(func.count()).where(
            BroadcastDelivery.channel == "whatsapp",
            BroadcastDelivery.status == "sent",
            BroadcastDelivery.sent_at >= since,
        )
    )
    return last, sent or 0


# ------------------------------------------------------------------ reading


def _stats(db: Session, ids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {i: {} for i in ids}
    if not ids:
        return out
    q = (
        select(BroadcastDelivery.broadcast_id, BroadcastDelivery.channel, BroadcastDelivery.status, func.count())
        .where(BroadcastDelivery.broadcast_id.in_(ids))
        .group_by(BroadcastDelivery.broadcast_id, BroadcastDelivery.channel, BroadcastDelivery.status)
    )
    for bid, channel, status, n in db.execute(q):
        out[bid].setdefault(channel, dict.fromkeys(STATS, 0))[status] = n
    return out


def _out(b: Broadcast, stats: dict) -> dict:
    return {
        "id": str(b.public_id),
        "title": b.title,
        "body": b.body,
        "audience": {k: v for k, v in b.audience.items() if not k.startswith("_")},
        "channels": list(b.channels),
        "status": b.status,
        "scheduled_at": b.scheduled_at,
        "recipients": b.recipients,
        "created_at": b.created_at,
        "started_at": b.started_at,
        "sent_at": b.sent_at,
        "cancelled_at": b.cancelled_at,
        "stats": stats,
    }


def list_broadcasts(db: Session, *, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0):
    query = select(Broadcast).order_by(Broadcast.id.desc())
    if status:
        query = query.where(Broadcast.status == status)
    if q:
        like = f"%{q}%"
        query = query.where(Broadcast.title["ar"].astext.ilike(like) | Broadcast.title["en"].astext.ilike(like))
    rows = list(db.scalars(query.limit(limit).offset(offset)))
    stats = _stats(db, [b.id for b in rows])
    return [_out(b, stats[b.id]) for b in rows]


def detail(db: Session, public_id) -> dict:
    b = _get(db, public_id)
    return _out(b, _stats(db, [b.id])[b.id])


def deliveries(
    db: Session, public_id, *, status: str | None = None, channel: str | None = None, limit: int = 50, offset: int = 0
) -> list[dict]:
    """Who got it and who did not, and why (the drill-down to failures)."""
    b = _get(db, public_id)
    q = select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == b.id).order_by(BroadcastDelivery.id)
    if status:
        q = q.where(BroadcastDelivery.status == status)
    if channel:
        q = q.where(BroadcastDelivery.channel == channel)
    rows = list(db.scalars(q.limit(limit).offset(offset)))
    names = people.names(db, [d.employee_id for d in rows])
    return [
        {
            "driver": names.get(d.employee_id),
            "channel": d.channel,
            "status": d.status,
            "reason": d.reason,
            "lang": d.lang,
            "attempts": d.attempts,
            "updated_at": d.updated_at,
            "sent_at": d.sent_at,
        }
        for d in rows
    ]
