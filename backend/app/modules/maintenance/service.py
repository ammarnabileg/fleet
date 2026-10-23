"""Maintenance requests, maintenance centers and their portal, and the centers' invoices (BRD 5.9, 5.10).

The flow: the driver (from the app) or the office picks the center, and the request reaches it at once: no approval,
no referral. The center receives the car with its odometer reading and photo; the car stays in its driver's custody,
"in maintenance": he does not work with it meanwhile (no start of day, no tracking alerts). When the repair is done
the center marks it ready for pickup in one step, with its invoice (file, number, total), which waits for the
management's approval (that decides the payment, not the pickup); the driver is told, collects the car and confirms
it in the app with his odometer reading and photo: it is his to work with again. The request closes once picked up
and, if the settings say so, once its invoice is approved. When nobody holds the car (the office took it back while
it was at the center, or none held it), the office or the center records the pickup and the car is available.

Requests from before this flow keep their history and can still finish: approval and referral of a request waiting
for them, the center's inspection, quote and repair steps; from any of those the center may mark the car ready with
its invoice. A vehicle in an accident keeps the accident's way (estimate, approval, the office's center).

Center accounts see only what was sent to their center: every portal function takes the user and resolves the
center itself. Every status change is a row in request_events: the timeline, who decided, and the time spent at the
center and in each status.
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, false, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import business_date, today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.maintenance.models import (
    AT_CENTER,
    Center,
    CenterUser,
    Invoice,
    InvoiceItem,
    Quote,
    Replacement,
    Request,
    RequestEvent,
    RequestPhoto,
    Schedule,
)
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

CENTER_ERRORS = {"centers_name_idx": "center_name_taken"}
REQUEST_ERRORS = {"requests_one_at_center_idx": "vehicle_at_center", "requests_client_ref_key": "request_exists"}
CANCELLABLE = ("requested", "approved", "referred")
QUOTE_FROM = ("received", "inspection", "in_repair", "waiting_parts")
INVOICE_FROM = ("completed", "ready", "picked_up", "closed")
READY_FROM = ("received", "inspection", "in_repair", "waiting_parts", "completed")  # quote_pending: decided first
PORTAL_MOVES = {"inspection": ("received",), "in_repair": ("waiting_parts",), "waiting_parts": ("in_repair",)}
HISTORY = ("picked_up", "closed", "cancelled")
UNDER_REPAIR = ("received", "inspection", "in_repair", "waiting_parts", "completed")
NOT_READY = ("referred", *UNDER_REPAIR, "quote_pending")  # at (or sent to) the center, not ready yet: may be late
FINISHED = ("rejected", "picked_up", "closed", "cancelled")
SCHEDULE_ERRORS = {"schedules_title_idx": "schedule_title_taken"}
READING_STALE = timedelta(days=30)  # an older last reading still counts, but the screens say how old it is
CENT = Decimal("0.001")
PHOTO_STAGES = {"request": 0, "reception": 1, "repair": 2}  # the order a request's photos are shown in


# ------------------------------------------------------------------ helpers


def _event(db: Session, r: Request, status: str, *, by_user=None, by_device=None, note=None, at=None) -> None:
    """A note starting with ":" is a code the screens translate (":quote_approved"); any other note is a person's."""
    r.status = status
    r.version += 1
    event = RequestEvent(request_id=r.id, status=status, by_user=by_user, by_device=by_device, note=note)
    if at is not None:  # otherwise the database's now(), like every other timestamp of the transaction
        event.at = at
    db.add(event)


def _flush(db: Session, errors: dict) -> None:
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        code = errors.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None


def _shortcut(db: Session, r: Request) -> bool:
    """A request sent straight to the center may be repaired without a quote, unless the office refused one the
    center sent for it: then the repair waits for a quote it approves, as any other."""
    if not r.direct:
        return False
    states = set(db.scalars(select(Quote.status).where(Quote.request_id == r.id)))
    return "rejected" not in states or "approved" in states


def _bookable(db: Session) -> list[Center]:
    """The centers a driver may take his car to: active, with an active portal account to receive it (a center
    the office only enters invoices for could never record the reception)."""
    centers = list(db.scalars(select(Center).where(Center.is_active.is_(True)).order_by(Center.name)))
    members = db.execute(
        select(CenterUser.center_id, CenterUser.user_id).where(CenterUser.center_id.in_([c.id for c in centers]))
    ).all()
    active = {u["user_id"] for u in identity.users_brief(db, [m.user_id for m in members]) if u["is_active"]}
    staffed = {m.center_id for m in members if m.user_id in active}
    return [c for c in centers if c.id in staffed]


def _scoped(q, all_companies: bool, company_ids: Iterable[int], column=Request.company_id):
    return q if all_companies else q.where(column.in_(list(company_ids)))


def _get(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Request:
    q = _scoped(select(Request).where(Request.public_id == public_id), all_companies, company_ids)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise AppError(404, "maintenance_request_not_found")
    return r


def _center_ref(c: Center | None) -> dict | None:
    if c is None:
        return None
    return {"id": str(c.public_id), "name": c.name, "phone": c.phone, "address": c.address}


def _items(raw: list[dict]) -> list[dict]:
    return [i | {"amount": (Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"]))).quantize(CENT)} for i in raw]


def _items_total(items: list[dict]) -> Decimal:
    return sum((Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"])) for i in items), Decimal(0)).quantize(CENT)


def _check_images(db: Session, shas: Iterable[str], *, user_id: int | None = None, device_id: int | None = None):
    """Photos must be images uploaded by the same account (a center user) or taken by the same phone's camera."""
    for sha in dict.fromkeys(shas):
        info = files.get(db, sha)
        if info.content_type not in files.IMAGES:
            raise AppError(422, "photo_must_be_image")
        if device_id is not None and (info.uploaded_by_device != device_id or info.source != "camera"):
            raise AppError(422, "file_not_yours")
        if user_id is not None and info.uploaded_by_user != user_id:
            raise AppError(422, "file_uploaded_by_other_account")  # the same bytes came from someone else first


def _check_document(db: Session, sha: str, *, user_id: int | None = None) -> None:
    info = files.get(db, sha)  # images or PDF: every type files accepts
    if user_id is not None and info.uploaded_by_user != user_id:
        raise AppError(422, "file_uploaded_by_other_account")


def _add_photos(db: Session, r: Request, stage: str, shas: Iterable[str]) -> None:
    existing = set(db.scalars(select(RequestPhoto.file_sha256).where(RequestPhoto.request_id == r.id)))
    for sha in dict.fromkeys(shas):
        if sha not in existing:
            db.add(RequestPhoto(request_id=r.id, stage=stage, file_sha256=sha))


def _alert_params(db: Session, r: Request) -> dict:
    return {"plate": fleet.plate_numbers(db, [r.vehicle_id]).get(r.vehicle_id, ""), "number": r.number}


def _approval(db: Session, r: Request, quote: Quote | None = None) -> dict:
    """The request, or its quote, as the approval workflows know it."""
    ref = f"MNT-{r.number} {fleet.plate_numbers(db, [r.vehicle_id]).get(r.vehicle_id, '')}".strip()
    if quote is not None:
        return {
            "document_id": quote.id,
            "document_key": quote.public_id,
            "document_ref": ref,
            "company_id": r.company_id,
            "amount": quote.amount,
        }
    return {
        "document_id": r.id,
        "document_key": r.public_id,
        "document_ref": ref,
        "company_id": r.company_id,
        "amount": Decimal(0),
    }


def _tell_driver(db: Session, r: Request, kind: str, **params) -> None:
    """The driver who asked for the repair (or held the vehicle when it was asked for) learns of it in the app."""
    if r.driver_id is not None:
        notifications.notify_driver(
            db,
            r.driver_id,
            kind,
            params={"number": r.number, **params},
            entity_type="maintenance_request",
            entity_id=r.public_id,
        )


def _invoice_approval(inv: Invoice) -> dict:
    return {
        "document_id": inv.id,
        "document_key": inv.public_id,
        "document_ref": f"INV-{inv.number}",
        "company_id": inv.company_id,
        "amount": inv.total,
    }


# ------------------------------------------------------------------ output


def _stay(r: Request, now: datetime) -> int | None:
    if r.received_at is None:
        return None
    return int(((r.picked_up_at or now) - r.received_at).total_seconds())


def _late(r: Request, settings, day: date) -> str | None:
    """Why a request not ready yet is late: past its expected date ("expected"), or at the center longer than the
    settings allow with no expected date ("long_stay"); None when it is not."""
    if r.status not in NOT_READY:
        return None
    if r.expected_ready_on is not None:
        return "expected" if r.expected_ready_on < day else None
    if settings.long_stay_days and r.received_at is not None:
        if (day - business_date(r.received_at)).days >= settings.long_stay_days:
            return "long_stay"
    return None


def _requests_out(db: Session, rows: list[Request], *, for_center: bool = False) -> list[dict]:
    cards = fleet.vehicle_cards(db, {r.vehicle_id for r in rows})
    names = {} if for_center else people.names(db, {r.driver_id for r in rows if r.driver_id})
    holders = {r.vehicle_id: fleet.holder(db, r.vehicle_id) for r in rows if r.status in AT_CENTER}
    center_ids = {r.center_id for r in rows if r.center_id}
    centers = {c.id: c for c in db.scalars(select(Center).where(Center.id.in_(center_ids)))} if center_ids else {}
    assignees = {} if for_center else identity.user_refs(db, {r.assignee_id for r in rows})
    schedule_ids = {r.schedule_id for r in rows if r.schedule_id}
    schedules = {
        i: {"id": str(p), "title": t}
        for i, p, t in (
            db.execute(select(Schedule.id, Schedule.public_id, Schedule.title).where(Schedule.id.in_(schedule_ids)))
            if schedule_ids
            else []
        )
    }
    settings = org.get_section(db, "maintenance")
    now, day = utcnow(), today()
    return [
        {
            "id": str(r.public_id),
            "number": r.number,
            "vehicle": cards.get(r.vehicle_id, {}),
            "company_id": r.company_id,
            "driver": names.get(r.driver_id),
            "kind": r.kind,
            "description": r.description,
            "odometer_km": r.odometer_km,
            "emergency": r.emergency,
            "emergency_reviewed": r.emergency_reviewed_at is not None,
            "status": r.status,
            "source": "driver" if r.created_by_device else "office",
            "direct": r.direct,
            "center": _center_ref(centers.get(r.center_id)),
            "created_at": r.created_at,
            "referred_at": r.referred_at,
            "received_at": r.received_at,
            "received_km": r.received_km,
            "ready_at": r.ready_at,
            "picked_up_at": r.picked_up_at,
            "closed_at": r.closed_at,
            "stay_seconds": _stay(r, now),
            "decision_note": r.decision_note,
            "cancel_reason": r.cancel_reason,
            "is_new": for_center and r.status == "referred" and r.seen_at is None,
            # at the center, a driver holds the car: he collects it and confirms it in the app
            "driver_collects": holders.get(r.vehicle_id) is not None,
            "priority": r.priority,
            "expected_ready_on": r.expected_ready_on,
            "late": (late := _late(r, settings, day)),
            "escalated": late is not None and r.escalated_at is not None,
            "assignee": assignees.get(r.assignee_id),
            "schedule": schedules.get(r.schedule_id),
            "version": r.version,
        }
        for r in rows
    ]


def _durations(events: list[RequestEvent], now: datetime) -> list[dict]:
    """Time in each status from the reception until the vehicle leaves the center (BRD FR-MNT-09)."""
    out, started = [], False
    for i, e in enumerate(events):
        started = started or e.status == "received"
        if not started:
            continue
        if e.status in HISTORY:
            break
        if out and out[-1]["status"] == e.status:
            continue  # a note on the same status (a replacement car, a new date): still the same stay
        nxt = next((x for x in events[i + 1 :] if x.status != e.status), None)
        end = nxt.at if nxt else None
        out.append(
            {
                "status": e.status,
                "started_at": e.at,
                "ended_at": end,
                "seconds": int(((end or now) - e.at).total_seconds()),
            }
        )
    return out


def _quote_out(q: Quote, users: dict) -> dict:
    return {
        "id": str(q.public_id),
        "amount": q.amount,
        "items": _items(q.items),
        "notes": q.notes,
        "has_file": q.file_sha256 is not None,
        "file_sha256": q.file_sha256,
        "status": q.status,
        "auto_approved": q.auto_approved,
        "created_at": q.created_at,
        "decided_at": q.decided_at,
        "decided_by": users.get(q.decided_by),
        "reason": q.reason,
    }


def _approved_quote(db: Session, request_id: int) -> Quote | None:
    return db.scalar(
        select(Quote)
        .where(Quote.request_id == request_id, Quote.status == "approved")
        .order_by(Quote.decided_at.desc(), Quote.id.desc())
        .limit(1)
    )


def _invoices_out(db: Session, rows: list[Invoice]) -> list[dict]:
    if not rows:
        return []
    ids = [i.id for i in rows]
    lines: dict[int, list[dict]] = {}
    for it in db.scalars(select(InvoiceItem).where(InvoiceItem.invoice_id.in_(ids)).order_by(InvoiceItem.line)):
        lines.setdefault(it.invoice_id, []).append(
            {"kind": it.kind, "description": it.description, "quantity": it.quantity, "unit_price": it.unit_price}
        )
    centers = {c.id: c for c in db.scalars(select(Center).where(Center.id.in_({i.center_id for i in rows})))}
    request_ids = {i.request_id for i in rows if i.request_id}
    requests = {r.id: r for r in db.scalars(select(Request).where(Request.id.in_(request_ids)))} if request_ids else {}
    plates = fleet.plate_numbers(db, {r.vehicle_id for r in requests.values()})
    users = identity.user_names(db, {u for i in rows for u in (i.created_by, i.decided_by)})
    quotes = {rid: _approved_quote(db, rid) for rid in request_ids}
    out = []
    for i in rows:
        r = requests.get(i.request_id)
        q = quotes.get(i.request_id)
        out.append(
            {
                "id": str(i.public_id),
                "center": _center_ref(centers[i.center_id]),
                "request": {"id": str(r.public_id), "number": r.number, "status": r.status} if r else None,
                "vehicle_plate": plates.get(r.vehicle_id) if r else None,
                "company_id": i.company_id,
                "number": i.number,
                "invoice_date": i.invoice_date,
                "total": i.total,
                "items": _items(lines.get(i.id, [])),
                "notes": i.notes,
                "file_sha256": i.file_sha256,
                "flags": list(i.flags),
                "quote_amount": q.amount if q else None,
                "status": i.status,
                "payment_status": i.payment_status,
                "paid_at": i.paid_at,
                "payment_ref": i.payment_ref,
                "created_at": i.created_at,
                "created_by": users.get(i.created_by),
                "decided_at": i.decided_at,
                "decided_by": users.get(i.decided_by),
                "reason": i.reason,
                "version": i.version,
            }
        )
    return out


def _detail(db: Session, r: Request, *, for_center: bool = False) -> dict:
    out = _requests_out(db, [r], for_center=for_center)[0]
    events = list(db.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id).order_by(RequestEvent.id)))
    quotes = list(db.scalars(select(Quote).where(Quote.request_id == r.id).order_by(Quote.id)))
    invoices = list(db.scalars(select(Invoice).where(Invoice.request_id == r.id).order_by(Invoice.id)))
    users = identity.user_names(db, {e.by_user for e in events} | {q.decided_by for q in quotes})
    driver_label = "driver"  # an action from the driver's phone
    photos = db.scalars(
        select(RequestPhoto)
        .where(RequestPhoto.request_id == r.id)
        # in the order they were taken (the primary key would sort them by their hash, which is to say at random)
        .order_by(case(PHOTO_STAGES, value=RequestPhoto.stage), RequestPhoto.file_sha256)
    )
    return (
        out
        | {
            "shortcut": _shortcut(db, r),
            "condition_note": r.condition_note,
            "repair_details": r.repair_details,
            "final_km": r.final_km,
            "completed_at": r.completed_at,
            "photos": [{"stage": p.stage, "sha256": p.file_sha256} for p in photos],
            "events": [
                {
                    "status": e.status,
                    "at": e.at,
                    "by": users.get(e.by_user) if e.by_user else (driver_label if e.by_device else None),
                    "note": e.note,
                }
                for e in events
            ],
            "durations": _durations(events, utcnow()),
            "quotes": [_quote_out(q, users) for q in quotes],
            "invoices": _invoices_out(db, invoices),
        }
        | ({} if for_center else _links(db, r, events))
    )


def _links(db: Session, r: Request, events: list[RequestEvent]) -> dict:
    """What the request is tied to, for the office: the custody the car was in (the driver who keeps it while it is
    at the center), the replacement cars given meanwhile, and the pickup (when, by whom, at what reading)."""
    at = r.received_at or r.created_at
    custody = fleet.custody_ref_at(db, r.vehicle_id, at)
    given = list(db.scalars(select(Replacement).where(Replacement.request_id == r.id).order_by(Replacement.created_at)))
    briefs = fleet.custodies_brief(db, [custody.id if custody else None, *(g.custody_id for g in given)])
    pickup = None
    if r.picked_up_at is not None:
        event = next((e for e in reversed(events) if e.status == "picked_up"), None)
        readings = fleet.readings_between(
            db, [r.vehicle_id], r.picked_up_at - timedelta(seconds=1), r.picked_up_at + timedelta(seconds=1)
        ).get(r.vehicle_id, [])
        by = None
        if event is not None:
            by = identity.user_names(db, [event.by_user]).get(event.by_user) if event.by_user else "driver"
        pickup = {"at": r.picked_up_at, "by": by, "km": readings[-1][1] if readings else r.final_km}
    return {
        "custody": briefs.get(custody.id) if custody else None,
        "replacements": [briefs[g.custody_id] for g in given if g.custody_id in briefs],
        "pickup": pickup,
    }


def _audit(db, action: str, r: Request, *, actor_user_id=None, actor_type=None, after=None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="maintenance_request",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        company_id=r.company_id,
        after={"number": r.number, "status": r.status} | (after or {}),
    )


def _emit(db, event_type: str, r: Request, **payload) -> None:
    emit(
        db,
        event_type,
        r.public_id,
        {"request_id": str(r.public_id), "number": r.number, "status": r.status} | payload,
    )


# ------------------------------------------------------------------ centers and their portal accounts


def _center(db: Session, public_id, *, lock=False) -> Center:
    q = select(Center).where(Center.public_id == public_id)
    c = db.scalar(q.with_for_update() if lock else q)
    if c is None:
        raise AppError(404, "center_not_found")
    return c


def _center_out(db: Session, centers: list[Center]) -> list[dict]:
    ids = [c.id for c in centers]
    users = dict(
        db.execute(
            select(CenterUser.center_id, func.count())
            .where(CenterUser.center_id.in_(ids))
            .group_by(CenterUser.center_id)
        ).all()
    )
    busy = dict(
        db.execute(
            select(Request.center_id, func.count())
            .where(Request.center_id.in_(ids), Request.status.in_(AT_CENTER))
            .group_by(Request.center_id)
        ).all()
    )
    return [
        {
            "id": str(c.public_id),
            "name": c.name,
            "specialty": c.specialty,
            "contact_name": c.contact_name,
            "phone": c.phone,
            "email": c.email,
            "address": c.address,
            "notes": c.notes,
            "is_active": c.is_active,
            "version": c.version,
            "users": users.get(c.id, 0),
            "at_center": busy.get(c.id, 0),
        }
        for c in centers
    ]


CENTER_FIELDS = ("name", "specialty", "contact_name", "phone", "email", "address", "notes", "is_active")


def list_centers(db: Session, *, active_only: bool = False) -> list[dict]:
    q = select(Center).order_by(Center.name)
    if active_only:
        q = q.where(Center.is_active.is_(True))
    return _center_out(db, list(db.scalars(q)))


def create_center(db: Session, data: dict, *, actor_user_id: int) -> dict:
    c = Center(**{f: data.get(f) for f in CENTER_FIELDS if f != "is_active"}, is_active=data.get("is_active", True))
    db.add(c)
    _flush(db, CENTER_ERRORS)
    db.refresh(c)
    out = _center_out(db, [c])[0]
    audit.record(
        db, action="center.created", entity_type="center", entity_id=c.public_id, actor_user_id=actor_user_id, after=out
    )
    db.commit()
    return out


def update_center(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int) -> dict:
    c = _center(db, public_id, lock=True)
    if c.version != version:
        raise AppError(409, "version_conflict")
    if "name" in changes and changes["name"] is None:
        raise AppError(422, "field_required", field="name")
    before = _center_out(db, [c])[0]
    for field in CENTER_FIELDS:
        if field in changes and not (field == "is_active" and changes[field] is None):
            setattr(c, field, changes[field])
    c.version += 1
    c.updated_at = func.now()
    _flush(db, CENTER_ERRORS)
    db.refresh(c)
    out = _center_out(db, [c])[0]
    audit.record(
        db,
        action="center.updated",
        entity_type="center",
        entity_id=c.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after=out,
    )
    db.commit()
    return out


def _portal_users_out(db: Session, center_id: int) -> list[dict]:
    ids = db.scalars(select(CenterUser.user_id).where(CenterUser.center_id == center_id))
    return [
        {
            "id": u["public_id"],
            "username": u["username"],
            "full_name": u["full_name"],
            "phone": u["phone"],
            "is_active": u["is_active"],
            "last_login_at": u["last_login_at"],
        }
        for u in identity.users_brief(db, ids)
    ]


def center_users(db: Session, public_id) -> list[dict]:
    return _portal_users_out(db, _center(db, public_id).id)


def add_center_user(db: Session, public_id, data: dict, *, actor_user_id: int) -> list[dict]:
    c = _center(db, public_id, lock=True)
    user_id = identity.create_portal_user(
        db,
        actor_user_id=actor_user_id,
        username=data["username"],
        full_name=data["full_name"],
        phone=data.get("phone"),
        password=data["password"],
    )
    db.add(CenterUser(user_id=user_id, center_id=c.id))
    db.commit()
    return _portal_users_out(db, c.id)


def link_center_user(db: Session, public_id, username: str, *, actor_user_id: int) -> list[dict]:
    """Links an existing portal-only account to this center (an account made from the users page links nowhere)."""
    c = _center(db, public_id, lock=True)
    user_id = identity.portal_user_id(db, username)
    linked = db.scalar(select(CenterUser).where(CenterUser.user_id == user_id))
    if linked is not None:
        raise AppError(409, "center_user_linked")
    db.add(CenterUser(user_id=user_id, center_id=c.id))
    audit.record(
        db,
        action="center.user_linked",
        entity_type="center",
        entity_id=c.public_id,
        actor_user_id=actor_user_id,
        after={"username": username},
    )
    db.commit()
    return _portal_users_out(db, c.id)


def set_center_user_active(db: Session, public_id, user_public_id, *, active: bool, actor_user_id: int) -> list[dict]:
    c = _center(db, public_id)
    members = {u["public_id"]: u["user_id"] for u in identity.users_brief(db, _member_ids(db, c.id))}
    if str(user_public_id) not in members:
        raise AppError(404, "user_not_found")
    identity.set_portal_user_active(db, members[str(user_public_id)], active=active, actor_user_id=actor_user_id)
    db.commit()
    return _portal_users_out(db, c.id)


def _member_ids(db: Session, center_id: int) -> list[int]:
    return list(db.scalars(select(CenterUser.user_id).where(CenterUser.center_id == center_id)))


def center_of(db: Session, user_id: int) -> Center:
    """The center a portal account works for. Everything the portal shows or changes goes through this."""
    c = db.scalar(
        select(Center).join(CenterUser, CenterUser.center_id == Center.id).where(CenterUser.user_id == user_id)
    )
    if c is None:
        raise AppError(403, "not_a_center_account")
    if not c.is_active:
        raise AppError(403, "center_inactive")
    return c


# ------------------------------------------------------------------ requests (office and driver)


def _send_to(db: Session, r: Request, center: Center, *, by_user=None, by_device=None) -> None:
    """The request reaches the center at once (one line on the timeline: who asked, and for which center)."""
    now = utcnow()
    r.status, r.center_id, r.decided_at, r.referred_at, r.direct = "referred", center.id, now, now, True
    if by_user is not None:
        r.decided_by, r.referred_by = by_user, by_user
    _flush(db, REQUEST_ERRORS)  # the database's rules for a request at a center: one per vehicle, a center set
    db.refresh(r)
    db.add(RequestEvent(request_id=r.id, status="requested", by_user=by_user, by_device=by_device, note=center.name))


def create_request(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    """From the office: the vehicle and the center it goes to; the request reaches the center at once."""
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope)
    if not data.get("center_id"):
        raise AppError(422, "center_required")
    center = _center(db, data["center_id"])
    if not center.is_active:
        raise AppError(409, "center_inactive")
    _check_images(db, data.get("photos") or [])
    schedule = None
    if data.get("schedule_id"):
        schedule = _schedule(db, data["schedule_id"], lock=True, **scope)
        if schedule.vehicle_id != vehicle.id or not schedule.active:
            raise AppError(422, "schedule_other_vehicle")
        if db.scalar(
            select(Request.id).where(Request.schedule_id == schedule.id, Request.status.notin_(FINISHED)).limit(1)
        ):
            raise AppError(409, "schedule_has_request")
    expected = data.get("expected_ready_on")
    if expected is not None and expected < today():
        raise AppError(422, "expected_in_past")
    r = Request(
        vehicle_id=vehicle.id,
        company_id=vehicle.company_id,
        driver_id=fleet.holder(db, vehicle.id),
        kind=data["kind"],
        description=data["description"],
        odometer_km=data.get("odometer_km"),
        emergency=data.get("emergency", False),
        created_by_user=actor_user_id,
        priority=data.get("priority") or ("high" if data.get("emergency") else "normal"),
        expected_ready_on=expected,
        assignee_id=identity.office_user(db, data["assignee_id"], "maintenance.view")
        if data.get("assignee_id")
        else None,
        schedule_id=schedule.id if schedule else None,
    )
    db.add(r)
    _send_to(db, r, center, by_user=actor_user_id)
    _add_photos(db, r, "request", data.get("photos") or [])
    _audit(db, "maintenance.requested", r, actor_user_id=actor_user_id, after={"center": center.name})
    _emit(db, "maintenance.request.referred", r, vehicle_id=str(vehicle.public_id), center_id=str(center.public_id))
    db.commit()
    return _detail(db, r)


def driver_request(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    """From the app, for the vehicle the driver holds, to the center he picked; photos from this phone's camera
    only. A vehicle in an accident goes through the office instead (its repair follows the accident: estimate,
    approval, the office's center), whatever center he picked."""
    if db.scalar(select(Request.id).where(Request.client_ref == data["client_ref"])):
        raise AppError(409, "request_exists")  # a retry: already recorded
    custody = fleet.open_custody_for_driver(db, employee_id)
    if custody is None:
        raise AppError(409, "no_vehicle_in_custody")
    _check_images(db, data.get("photos") or [], device_id=device_id)
    accident = fleet.vehicle_cards(db, [custody.vehicle_id])[custody.vehicle_id]["status"] == "accident"
    center = None
    if not accident:
        if not data.get("center_id"):
            raise AppError(422, "center_required")
        center = _center(db, data["center_id"])
        if center.id not in {c.id for c in _bookable(db)}:
            raise AppError(409, "center_inactive")
    r = Request(
        vehicle_id=custody.vehicle_id,
        company_id=custody.company_id,
        driver_id=employee_id,
        kind=data["kind"],
        description=data["description"],
        odometer_km=data.get("odometer_km"),
        client_ref=data["client_ref"],
        created_by_device=device_id,
    )
    db.add(r)
    if center is not None:
        _send_to(db, r, center, by_device=device_id)
        _add_photos(db, r, "request", data.get("photos") or [])
        _audit(db, "maintenance.requested", r, actor_type="device", after={"center": center.name})
        _emit(db, "maintenance.request.referred", r, center_id=str(center.public_id))
        db.commit()
        return for_driver(db, employee_id, only=r.id)[0]
    _flush(db, REQUEST_ERRORS)
    db.refresh(r)
    db.add(RequestEvent(request_id=r.id, status="requested", by_device=device_id, note=":accident_vehicle"))
    _add_photos(db, r, "request", data.get("photos") or [])
    notifications.raise_alert(
        db,
        "maintenance_requested",
        company_id=r.company_id,
        entity_type="maintenance_request",
        entity_id=r.public_id,
        params=_alert_params(db, r),
        dedupe_key=f"mnt_request:{r.id}",
    )
    approvals.submitted(db, "maintenance_request", **_approval(db, r))
    _audit(db, "maintenance.requested", r, actor_type="device", after={"accident": True})
    _emit(db, "maintenance.request.created", r, emergency=False)
    db.commit()
    return for_driver(db, employee_id, only=r.id)[0]


def for_driver(db: Session, employee_id: int, *, limit: int = 20, only: int | None = None) -> list[dict]:
    """His requests, and the open ones of the cars he holds now (asked for while another driver held it): his own,
    and a replacement while his own is at the center."""
    held = {
        c.vehicle_id
        for c in (fleet.own_custody_for_driver(db, employee_id), fleet.open_custody_for_driver(db, employee_id))
        if c
    }
    mine = Request.driver_id == employee_id
    if held:
        mine = or_(mine, and_(Request.vehicle_id.in_(held), Request.status.in_(AT_CENTER)))
    q = select(Request).where(mine)
    if only is not None:
        q = q.where(Request.id == only)
    rows = list(db.scalars(q.order_by(Request.created_at.desc(), Request.id.desc()).limit(limit)))
    plates = fleet.plate_numbers(db, {r.vehicle_id for r in rows})
    holders = {r.vehicle_id: fleet.holder(db, r.vehicle_id) for r in rows if r.status == "ready"}
    center_ids = {r.center_id for r in rows if r.center_id}
    centers = {c.id: c for c in db.scalars(select(Center).where(Center.id.in_(center_ids)))} if center_ids else {}
    replacing = {r.id: _open_replacement(db, r) for r in rows if r.status in AT_CENTER}
    return [
        {
            "id": str(r.public_id),
            "number": r.number,
            "vehicle_plate": plates.get(r.vehicle_id, ""),
            # the replacement car he holds meanwhile: he gives its reading too when he collects his own
            "replacement_plate": replacing[r.id][1]["vehicle"]["plate_number"] if replacing.get(r.id) else None,
            "kind": r.kind,
            "description": r.description,
            "status": r.status,
            "center": _center_ref(centers.get(r.center_id)),
            "created_at": r.created_at,
            "ready_at": r.ready_at,
            "picked_up_at": r.picked_up_at,
            "decision_note": r.decision_note if r.status == "rejected" else None,
            "direct": r.direct,
            # ready, and his to collect: he confirms the pickup in the app (otherwise the office records it)
            "pickup_in_app": r.status == "ready"
            and (
                holders.get(r.vehicle_id) == employee_id
                or (r.direct and holders.get(r.vehicle_id) is None and _left_at_reception(db, r, employee_id))
            ),
        }
        for r in rows
    ]


def driver_form(db: Session) -> dict:
    """What the app's request form offers: the centers he may take the car to (active, with a portal account)."""
    return {
        "direct_to_center": True,  # always, now: an older app reads it to show the centers
        "centers": [_center_ref(c) | {"specialty": c.specialty} for c in _bookable(db)],
    }


def _left_at_reception(db: Session, r: Request, employee_id: int) -> bool:
    """A request from before the simple flow: the reception ended his custody (at that very moment)."""
    if r.received_at is None:
        return False
    return any(
        c.vehicle_id == r.vehicle_id and c.ended_at == r.received_at
        for c in fleet.custodies_for_driver(db, employee_id, r.received_at - timedelta(seconds=1), r.received_at)
    )


def center_holding(db: Session, custody_public_id) -> str | None:
    """The center the custody's car is at now (the app's "your car is at the center")."""
    custody = fleet.custody_ref_by_public_id(db, custody_public_id, all_companies=True, company_ids=())
    return db.scalar(
        select(Center.name)
        .join(Request, Request.center_id == Center.id)
        .where(Request.vehicle_id == custody.vehicle_id, Request.status.in_(READY_FROM + ("quote_pending", "ready")))
        .limit(1)
    )


def driver_picked_up(db: Session, public_id, *, employee_id: int, device_id: int, data: dict) -> dict:
    """The driver collected his car from the center, with his odometer reading and camera photo. It never left his
    custody: the reading closes the stay and he works with it again. A request from before the simple flow, whose
    reception ended his custody, gives it back to him (a new custody). When the office took it back from him while
    it was at the center, the office records the pickup."""
    r = db.scalar(select(Request).where(Request.public_id == public_id).with_for_update())
    holder = fleet.holder(db, r.vehicle_id) if r is not None else None
    if r is None or (r.driver_id != employee_id and holder != employee_id):
        raise AppError(404, "maintenance_request_not_found")
    if r.status in ("picked_up", "closed"):
        mine = db.scalar(
            select(RequestEvent.id).where(
                RequestEvent.request_id == r.id, RequestEvent.status == "picked_up", RequestEvent.by_device == device_id
            )
        )
        # his own pickup sent again (the app's queue) is done; one the office recorded did not give him the car
        raise AppError(409, "already_picked_up" if mine else "pickup_by_office")
    if r.status != "ready":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    handing_back = holder is None and r.direct and _left_at_reception(db, r, employee_id)
    if holder != employee_id and not handing_back:
        raise AppError(409, "pickup_by_office")  # the car is no longer his: the office records it and hands over
    _check_images(db, [data["odometer_photo"]], device_id=device_id)
    now = utcnow()
    at = data.get("picked_up_at") or now
    # when the photo was taken: after the car was ready, not in the future, and late by two days at most
    if at > now + fleet.CLOCK_SKEW or at < now - fleet.DRIVER_READING_DELAY or (r.ready_at and at < r.ready_at):
        raise AppError(422, "invalid_recorded_at")
    replacement = _open_replacement(db, r)
    if replacement is not None:
        # he hands the replacement car back as he collects his own: its reading and camera photo, in the same step
        if data.get("replacement_odometer_km") is None or not data.get("replacement_odometer_photo"):
            raise AppError(422, "replacement_reading_required", plate=replacement[1]["vehicle"]["plate_number"])
        _check_images(db, [data["replacement_odometer_photo"]], device_id=device_id)
        _end_replacement(
            db,
            r,
            replacement,
            device_id=device_id,
            odometer_km=data["replacement_odometer_km"],
            photo_sha256=data["replacement_odometer_photo"],
            at=at,
        )
    if handing_back:
        released_by = db.scalar(  # the center account that called him: it gives the vehicle back
            select(RequestEvent.by_user)
            .where(RequestEvent.request_id == r.id, RequestEvent.status == "ready")
            .order_by(RequestEvent.id.desc())
            .limit(1)
        )
        _picked_up(db, r, by_device=device_id, at=at)
        fleet.hand_back_after_maintenance(
            db,
            r.vehicle_id,
            employee_id,
            odometer_km=data["odometer_km"],
            photo_sha256=data["odometer_photo"],
            at=at,
            handed_over_by=released_by or r.received_by,
            device_id=device_id,
        )
    else:
        fleet.collected_from_maintenance(
            db,
            r.vehicle_id,
            employee_id,
            odometer_km=data["odometer_km"],
            photo_sha256=data["odometer_photo"],
            at=at,
            device_id=device_id,
        )
        _picked_up(db, r, by_device=device_id, at=at)
    db.commit()
    return for_driver(db, employee_id, only=r.id)[0]


def list_requests(
    db: Session,
    *,
    status: str | None = None,
    active: bool | None = None,
    vehicle_public_id=None,
    center_public_id=None,
    custody_public_id=None,
    late: bool = False,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Request), **scope)
    if status:
        q = q.where(Request.status.in_(status.split(",")))
    if active is True:
        q = q.where(Request.status.notin_(("rejected", "closed", "cancelled")))
    if late:
        q = q.where(_late_clause(org.get_section(db, "maintenance")))
    if custody_public_id:
        # the requests of the custody's car while it held it, and those that gave it as a replacement
        c = fleet.custody_ref_by_public_id(db, custody_public_id, **scope)
        at = func.coalesce(Request.received_at, Request.created_at)
        q = q.where(
            or_(
                and_(
                    Request.vehicle_id == c.vehicle_id,
                    at >= c.started_at,
                    true() if c.ended_at is None else at < c.ended_at,
                ),
                Request.id.in_(select(Replacement.request_id).where(Replacement.custody_id == c.id)),
            )
        )
    if vehicle_public_id:
        q = q.where(Request.vehicle_id == fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id)
    if center_public_id:
        q = q.where(Request.center_id == _center(db, center_public_id).id)
    rows = db.scalars(q.order_by(Request.created_at.desc(), Request.id.desc()).limit(min(limit, 500)).offset(offset))
    return _requests_out(db, list(rows))


def _late_clause(settings):
    """SQL for _late: not ready, and past its expected date or (none given) at the center too long."""
    received_on = func.date(func.timezone("Asia/Kuwait", Request.received_at))
    stay = received_on <= today() - timedelta(days=settings.long_stay_days)
    return and_(
        Request.status.in_(NOT_READY),
        or_(
            Request.expected_ready_on < today(),
            and_(Request.expected_ready_on.is_(None), stay) if settings.long_stay_days else false(),
        ),
    )


def get_request(db: Session, public_id, **scope) -> dict:
    return _detail(db, _get(db, public_id, **scope))


def approve(db: Session, public_id, *, note: str | None, actor_user_id: int, **scope) -> dict:
    r = _get(db, public_id, lock=True, **scope)
    if r.status != "requested":
        raise AppError(409, "request_not_pending", status=r.status)
    if not approvals.gate(db, "maintenance_request", **_approval(db, r), actor_user_id=actor_user_id, reason=note):
        db.commit()  # this step recorded; the request waits for the next one
        return _detail(db, r)
    r.decided_by, r.decided_at, r.decision_note = actor_user_id, utcnow(), note
    _event(db, r, "approved", by_user=actor_user_id, note=note)
    _tell_driver(db, r, "maintenance_approved")
    notifications.resolve(db, f"mnt_request:{r.id}")
    _audit(db, "maintenance.approved", r, actor_user_id=actor_user_id, after={"note": note})
    _emit(db, "maintenance.request.approved", r)
    db.commit()
    return _detail(db, r)


def reject(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    r = _get(db, public_id, lock=True, **scope)
    if r.status != "requested":
        raise AppError(409, "request_not_pending", status=r.status)
    approvals.gate(
        db, "maintenance_request", **_approval(db, r), actor_user_id=actor_user_id, approve=False, reason=reason
    )
    r.decided_by, r.decided_at, r.decision_note = actor_user_id, utcnow(), reason
    _event(db, r, "rejected", by_user=actor_user_id, note=reason)
    _tell_driver(db, r, "maintenance_rejected", reason=reason)
    notifications.resolve(db, f"mnt_request:{r.id}")
    _audit(db, "maintenance.rejected", r, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _detail(db, r)


def review_emergency(db: Session, public_id, *, note: str | None, actor_user_id: int, **scope) -> dict:
    r = _get(db, public_id, lock=True, **scope)
    if not r.emergency or r.emergency_reviewed_at is not None:
        raise AppError(409, "not_awaiting_review")
    r.emergency_reviewed_by, r.emergency_reviewed_at = actor_user_id, utcnow()
    r.version += 1
    db.add(RequestEvent(request_id=r.id, status=r.status, by_user=actor_user_id, note=note or ":emergency_reviewed"))
    notifications.resolve(db, f"mnt_emergency:{r.id}")
    _audit(db, "maintenance.emergency_reviewed", r, actor_user_id=actor_user_id, after={"note": note})
    db.commit()
    return _detail(db, r)


def refer(db: Session, public_id, *, center_public_id, note: str | None, actor_user_id: int, **scope) -> dict:
    """Sends the approved request to a center (or to another one, as long as the vehicle has not arrived)."""
    r = _get(db, public_id, lock=True, **scope)
    if r.status not in ("approved", "referred"):
        raise AppError(409, "request_not_approved", status=r.status)
    center = _center(db, center_public_id)
    if not center.is_active:
        raise AppError(409, "center_inactive")
    if r.status == "referred" and r.center_id == center.id:
        return _detail(db, r)
    r.center_id, r.referred_by, r.referred_at, r.seen_at = center.id, actor_user_id, utcnow(), None
    _event(db, r, "referred", by_user=actor_user_id, note=f"{center.name}" + (f" — {note}" if note else ""))
    _flush(db, REQUEST_ERRORS)
    _audit(db, "maintenance.referred", r, actor_user_id=actor_user_id, after={"center": center.name})
    _emit(db, "maintenance.request.referred", r, center_id=str(center.public_id))
    db.commit()
    return _detail(db, r)


def cancel(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    r = _get(db, public_id, lock=True, **scope)
    if r.status not in CANCELLABLE:
        raise AppError(409, "request_cannot_cancel", status=r.status)
    r.cancel_reason = reason
    _event(db, r, "cancelled", by_user=actor_user_id, note=reason)
    _resolve_late(db, r)
    approvals.withdrawn(db, "maintenance_request", [r.id])
    notifications.resolve(db, f"mnt_request:{r.id}")
    _audit(db, "maintenance.cancelled", r, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _detail(db, r)


def picked_up(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    """The company collected the vehicle (recorded in the office): only when no driver holds it."""
    r = _get(db, public_id, lock=True, **scope)
    _check_office_pickup(db, r)
    _picked_up(db, r, actor_user_id)
    db.commit()
    return _detail(db, r)


def _follow_holder(db: Session, r: Request, actor_user_id: int) -> None:
    """The car changed hands since it was asked for: the request follows the driver who holds it now (he is told
    it is ready, sees it, and collects it)."""
    holder = fleet.holder(db, r.vehicle_id)
    if holder is None or holder == r.driver_id:
        return
    before, r.driver_id = r.driver_id, holder
    db.add(RequestEvent(request_id=r.id, status=r.status, by_user=actor_user_id, note=":driver_changed"))
    _audit(db, "maintenance.driver_changed", r, actor_user_id=actor_user_id, after={"from": before, "to": holder})


def _check_office_pickup(db: Session, r: Request) -> None:
    """The driver who holds the car collects it and confirms it in the app; the office or the center records the
    pickup only of a car nobody holds, once a replacement car given meanwhile is back."""
    if r.status == "ready" and fleet.holder(db, r.vehicle_id) is not None:
        raise AppError(409, "pickup_by_driver")
    if _open_replacement(db, r) is not None:
        raise AppError(409, "replacement_open")


def _picked_up(
    db: Session, r: Request, actor_user_id: int | None = None, *, by_device: int | None = None, at=None
) -> None:
    if r.status != "ready":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    r.picked_up_at, r.picked_up_by = at or utcnow(), actor_user_id
    _event(db, r, "picked_up", by_user=actor_user_id, by_device=by_device, at=at)
    fleet.released_from_maintenance(db, r.vehicle_id)
    notifications.resolve(db, f"mnt_ready:{r.id}")
    _resolve_late(db, r)
    _schedule_from_pickup(db, r, r.picked_up_at)
    _audit(
        db,
        "maintenance.picked_up",
        r,
        actor_user_id=actor_user_id,
        actor_type="device" if by_device else None,
        after={"stay_seconds": _stay(r, utcnow())},
    )
    _emit(db, "maintenance.vehicle.picked_up", r)
    _maybe_close(db, r, actor_user_id)


def _maybe_close(db: Session, r: Request, actor_user_id: int | None) -> None:
    """Closed once picked up and, if the settings say so, once its invoices are approved (BRD FR-MNT-12)."""
    if r.status != "picked_up":
        return
    if org.get_section(db, "maintenance").close_requires_invoice:
        states = set(db.scalars(select(Invoice.status).where(Invoice.request_id == r.id)))
        if "approved" not in states or "pending" in states:
            return
    r.closed_at = utcnow()
    _event(db, r, "closed", by_user=actor_user_id)


# ------------------------------------------------------------------ quotes (decided in the office)


def decide_quote(db: Session, public_id, *, approve: bool, reason: str | None, actor_user_id: int, **scope) -> dict:
    q = db.scalar(select(Quote).where(Quote.public_id == public_id).with_for_update())
    if q is None:
        raise AppError(404, "quote_not_found")
    r = db.scalar(_scoped(select(Request).where(Request.id == q.request_id), **scope).with_for_update())
    if r is None:
        raise AppError(404, "quote_not_found")
    if q.status != "pending":
        raise AppError(409, "quote_not_pending")
    if not approve and not reason:
        raise AppError(422, "reason_required")
    if not approvals.gate(
        db, "maintenance_quote", **_approval(db, r, q), actor_user_id=actor_user_id, approve=approve, reason=reason
    ):
        db.commit()  # this step recorded; the quote waits for the next one
        return _detail(db, r)
    q.status = "approved" if approve else "rejected"
    q.decided_by, q.decided_at, q.reason = actor_user_id, utcnow(), reason
    if approve:
        _event(db, r, "in_repair", by_user=actor_user_id, note=":quote_approved")
    else:  # back to the center for a new quote
        _event(db, r, "inspection", by_user=actor_user_id, note=reason)
    notifications.resolve(db, f"mnt_quote:{q.id}")
    _audit(
        db,
        "maintenance.quote_approved" if approve else "maintenance.quote_rejected",
        r,
        actor_user_id=actor_user_id,
        after={"amount": q.amount, "reason": reason},
    )
    db.commit()
    return _detail(db, r)


# ------------------------------------------------------------------ the center's portal


def _for_center(db: Session, public_id, center: Center, *, lock=False) -> Request:
    q = select(Request).where(Request.public_id == public_id, Request.center_id == center.id)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:  # referred elsewhere, or never: the portal does not even confirm it exists (UAT-21)
        raise AppError(404, "maintenance_request_not_found")
    return r


def portal_requests(db: Session, *, user_id: int, active: bool = True, limit: int = 100) -> list[dict]:
    center = center_of(db, user_id)
    q = select(Request).where(Request.center_id == center.id)
    q = q.where(Request.status.in_(AT_CENTER)) if active else q.where(Request.status.in_(HISTORY))
    rows = db.scalars(q.order_by(Request.referred_at.desc(), Request.id.desc()).limit(min(limit, 300)))
    return _requests_out(db, list(rows), for_center=True)


def portal_request(db: Session, public_id, *, user_id: int) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center)
    if r.seen_at is None:
        r.seen_at = utcnow()
        db.commit()
    return _detail(db, r, for_center=True)


def portal_center(db: Session, *, user_id: int) -> dict:
    c = center_of(db, user_id)
    return {
        "id": str(c.public_id),
        "name": c.name,
        "phone": c.phone,
        "address": c.address,
        "direct_to_center": True,  # requests come straight from the driver or the office
    }


def receive(db: Session, public_id, *, user_id: int, data: dict) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.status != "referred":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    at = data.get("received_at") or utcnow()
    _check_images(db, [data["odometer_photo"], *(data.get("photos") or [])], user_id=user_id)
    held = fleet.received_for_maintenance(
        db,
        r.vehicle_id,
        odometer_km=data["odometer_km"],
        photo_sha256=data["odometer_photo"],
        at=at,
        actor_user_id=user_id,
    )
    r.received_at, r.received_by, r.received_km = at, user_id, data["odometer_km"]
    _follow_holder(db, r, user_id)
    r.condition_note = data.get("condition_note")
    r.seen_at = r.seen_at or utcnow()
    _event(db, r, "received", by_user=user_id, at=at, note=data.get("condition_note"))
    if _approved_quote(db, r.id) is not None:  # an accident repair: its damage estimate was approved already
        _event(db, r, "in_repair", by_user=user_id, note=":accident_estimate")
    _add_photos(db, r, "reception", [data["odometer_photo"], *(data.get("photos") or [])])
    _audit(
        db,
        "maintenance.received",
        r,
        actor_user_id=user_id,
        after={"odometer_km": data["odometer_km"], "in_custody": bool(held)},
    )
    _emit(db, "maintenance.vehicle.received", r, center_id=str(center.public_id))
    db.commit()
    return _detail(db, r, for_center=True)


def set_status(db: Session, public_id, *, user_id: int, status: str, note: str | None) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.direct:  # the simple flow: reception, then ready with the invoice; no step in between
        raise AppError(409, "step_not_in_this_flow")
    # the repair itself starts only through an approved quote (submit_quote, decide_quote): "in_repair" here is
    # only the way back from waiting for parts. Straight to the center, the center starts it without one.
    allowed = PORTAL_MOVES[status] + (("received", "inspection") if status == "in_repair" and _shortcut(db, r) else ())
    if r.status not in allowed:
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    _event(db, r, status, by_user=user_id, note=note)
    _audit(db, "maintenance.status", r, actor_user_id=user_id, after={"note": note})
    db.commit()
    return _detail(db, r, for_center=True)


def submit_quote(db: Session, public_id, *, user_id: int, data: dict) -> dict:
    """Within the approval limit the quote is approved at once and the repair may start; above it the request
    waits for the maintenance manager (BRD FR-MNT-07)."""
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.direct:  # the simple flow: reception, then ready with the invoice; no step in between
        raise AppError(409, "step_not_in_this_flow")
    if r.status not in QUOTE_FROM:
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    items = [dict(i) for i in data.get("items") or []]
    amount = Decimal(data["amount"]).quantize(CENT)
    if items and _items_total(items) != amount:
        raise AppError(422, "quote_items_mismatch", total=str(amount), items=str(_items_total(items)))
    if data.get("file_sha256"):
        _check_document(db, data["file_sha256"], user_id=user_id)
    limit = org.get_section(db, "maintenance").approval_limit
    auto = amount <= limit
    q = Quote(
        request_id=r.id,
        amount=amount,
        items=[{k: str(v) if isinstance(v, Decimal) else v for k, v in i.items()} for i in items],
        notes=data.get("notes"),
        file_sha256=data.get("file_sha256"),
        status="approved" if auto else "pending",
        auto_approved=auto,
        created_by=user_id,
        decided_at=utcnow() if auto else None,
    )
    db.add(q)
    _flush(db, {"quotes_one_pending_idx": "quote_pending_exists"})
    if auto:
        if r.status in ("received", "inspection"):
            _event(db, r, "in_repair", by_user=user_id, note=":quote_within_limit")
    else:
        _event(db, r, "quote_pending", by_user=user_id)
        db.refresh(q)
        approvals.submitted(db, "maintenance_quote", **_approval(db, r, q), actor_user_id=user_id)
        notifications.raise_alert(
            db,
            "maintenance_quote_pending",
            company_id=r.company_id,
            entity_type="maintenance_request",
            entity_id=r.public_id,
            params=_alert_params(db, r) | {"center": center.name, "amount": str(amount), "limit": str(limit)},
            dedupe_key=f"mnt_quote:{q.id}",
        )
    _audit(db, "maintenance.quote_submitted", r, actor_user_id=user_id, after={"amount": amount, "auto": auto})
    db.commit()
    return _detail(db, r, for_center=True)


def complete(db: Session, public_id, *, user_id: int, data: dict) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.direct:  # the simple flow: reception, then ready with the invoice; no step in between
        raise AppError(409, "step_not_in_this_flow")
    # straight to the center, a short job goes from the reception to done (no quote, no separate start)
    done_from = ("in_repair", "waiting_parts") + (("received", "inspection") if _shortcut(db, r) else ())
    if r.status not in done_from:
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    _check_images(db, [data["final_odometer_photo"], *(data.get("photos") or [])], user_id=user_id)
    now = utcnow()
    fleet.maintenance_reading(
        db,
        r.vehicle_id,
        odometer_km=data["final_odometer_km"],
        photo_sha256=data["final_odometer_photo"],
        at=now,
        actor_user_id=user_id,
    )
    r.repair_details, r.final_km, r.completed_at = data["repair_details"], data["final_odometer_km"], now
    _event(db, r, "completed", by_user=user_id)
    _add_photos(db, r, "repair", [data["final_odometer_photo"], *(data.get("photos") or [])])
    _audit(db, "maintenance.completed", r, actor_user_id=user_id, after={"final_km": r.final_km})
    db.commit()
    return _detail(db, r, for_center=True)


def ready(db: Session, public_id, *, user_id: int, data: dict, can_invoice: bool = True) -> dict:
    """Ready for pickup, in one step with the center's invoice (file, number, total; its items and notes if it
    gives them), which waits for the management's approval. The driver is told in the app (BRD FR-MNT-10). When
    nobody holds the car the office is alerted to collect it, and the center gives its odometer reading at the end of
    the repair (the next handover is compared with it: a test drive is not distance off duty). A request that already
    has its invoice (from before the simple flow) is marked ready without another."""
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.status not in READY_FROM:
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    has_invoice = db.scalar(select(Invoice.id).where(Invoice.request_id == r.id, Invoice.status != "rejected").limit(1))
    reading = {k: data.pop(k, None) for k in ("final_odometer_km", "final_odometer_photo")}
    if not has_invoice or any(data.get(k) for k in ("file_sha256", "number", "total")):
        if not can_invoice:
            raise AppError(403, "permission_denied", permission="portal.invoices")
        data = {"invoice_date": today()} | {k: v for k, v in data.items() if v is not None}
        if not data.get("items") and data.get("total") is not None:
            data["items"] = [{"kind": "other", "description": r.description[:300], "unit_price": data["total"]}]
        for item in data.get("items") or []:
            item.setdefault("quantity", Decimal(1))
        _new_invoice(db, center=center, r=r, company_id=r.company_id, data=data, actor=user_id, own_file=True)
    _follow_holder(db, r, user_id)
    held = fleet.holder(db, r.vehicle_id) is not None
    # the company collects it: the next handover compares with the center's last reading (unless it gave one when
    # the repair was completed, before the simple flow)
    if not held and r.final_km is None:
        km, photo = reading["final_odometer_km"], reading["final_odometer_photo"]
        if km is None or not photo:
            raise AppError(422, "final_reading_required")
        _check_images(db, [photo], user_id=user_id)
        fleet.maintenance_reading(
            db, r.vehicle_id, odometer_km=km, photo_sha256=photo, at=utcnow(), actor_user_id=user_id
        )
        r.final_km = km
        _add_photos(db, r, "repair", [photo])
    r.ready_at = utcnow()
    _event(db, r, "ready", by_user=user_id)
    _resolve_late(db, r)
    if not held:  # nobody to collect it from the app: the office does
        notifications.raise_alert(
            db,
            "maintenance_ready",
            company_id=r.company_id,
            entity_type="maintenance_request",
            entity_id=r.public_id,
            params=_alert_params(db, r) | {"center": center.name},
            dedupe_key=f"mnt_ready:{r.id}",
        )
    _tell_driver(db, r, "maintenance_ready", center=center.name)
    _audit(db, "maintenance.ready", r, actor_user_id=user_id)
    _emit(db, "maintenance.vehicle.ready", r, center_id=str(center.public_id))
    db.commit()
    return _detail(db, r, for_center=True)


def portal_picked_up(db: Session, public_id, *, user_id: int) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    _check_office_pickup(db, r)
    _picked_up(db, r, user_id)
    db.commit()
    return _detail(db, r, for_center=True)


def portal_file(db: Session, public_id, sha256: str, *, user_id: int) -> files.FileInfo:
    center = center_of(db, user_id)
    return _request_file(db, _for_center(db, public_id, center), sha256)


def request_file(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    return _request_file(db, _get(db, public_id, **scope), sha256)


def _request_file(db: Session, r: Request, sha256: str) -> files.FileInfo:
    owned = (
        db.get(RequestPhoto, (r.id, sha256)) is not None
        or db.scalar(select(Quote.id).where(Quote.request_id == r.id, Quote.file_sha256 == sha256).limit(1))
        or db.scalar(select(Invoice.id).where(Invoice.request_id == r.id, Invoice.file_sha256 == sha256).limit(1))
    )
    if not owned:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


# ------------------------------------------------------------------ invoices


def _new_invoice(
    db: Session, *, center: Center, r: Request | None, company_id: int, data: dict, actor: int, own_file: bool
) -> Invoice:
    """UAT-22: a missing file, number or total is refused and named. UAT-23: a number already used by the same
    center is accepted, flagged and alerted. FR-INV-04: a total different from the approved quote too."""
    if not data.get("file_sha256"):
        raise AppError(422, "invoice_file_required")
    if not data.get("number"):
        raise AppError(422, "invoice_number_required")
    if data.get("total") is None or Decimal(data["total"]) <= 0:
        raise AppError(422, "invoice_total_required")
    if data.get("invoice_date") is None:
        raise AppError(422, "invoice_date_required")
    if data["invoice_date"] > today():
        raise AppError(422, "invoice_date_in_future")
    items = [dict(i) for i in data.get("items") or []]
    if not items:
        raise AppError(422, "invoice_items_required")
    total = Decimal(data["total"]).quantize(CENT)
    if _items_total(items) != total:
        raise AppError(422, "invoice_items_mismatch", total=str(total), items=str(_items_total(items)))
    _check_document(db, data["file_sha256"], user_id=actor if own_file else None)  # a center sends its own scans
    flags = []
    repeated = db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(
            Invoice.center_id == center.id,
            func.lower(Invoice.number) == data["number"].lower(),
            Invoice.status != "rejected",
        )
    )
    if repeated:
        flags.append("duplicate_number")
    quote = _approved_quote(db, r.id) if r is not None else None
    if quote is not None and quote.amount != total:
        flags.append("differs_from_quote")
    inv = Invoice(
        center_id=center.id,
        request_id=r.id if r else None,
        company_id=company_id,
        number=data["number"],
        invoice_date=data["invoice_date"],
        total=total,
        file_sha256=data["file_sha256"],
        notes=data.get("notes"),
        flags=flags,
        created_by=actor,
    )
    db.add(inv)
    db.flush()
    db.refresh(inv)
    for n, it in enumerate(items, start=1):
        db.add(
            InvoiceItem(
                invoice_id=inv.id,
                line=n,
                kind=it["kind"],
                description=it["description"],
                quantity=it["quantity"],
                unit_price=it["unit_price"],
            )
        )
    approvals.submitted(db, "maintenance_invoice", **_invoice_approval(inv), actor_user_id=actor)
    base = {"center": center.name, "number": inv.number, "total": str(total)}
    notifications.raise_alert(
        db,
        "maintenance_invoice_pending",
        company_id=company_id,
        entity_type="maintenance_invoice",
        entity_id=inv.public_id,
        params=base,
        dedupe_key=f"mnt_invoice:{inv.id}",
    )
    if "duplicate_number" in flags:
        notifications.raise_alert(
            db,
            "maintenance_invoice_duplicate",
            company_id=company_id,
            entity_type="maintenance_invoice",
            entity_id=inv.public_id,
            params=base,
            dedupe_key=f"mnt_invoice_dup:{inv.id}",
        )
    if "differs_from_quote" in flags:
        notifications.raise_alert(
            db,
            "maintenance_invoice_differs",
            company_id=company_id,
            entity_type="maintenance_invoice",
            entity_id=inv.public_id,
            params=base | {"quote": str(quote.amount)},
            dedupe_key=f"mnt_invoice_diff:{inv.id}",
        )
    audit.record(
        db,
        action="maintenance.invoice_submitted",
        entity_type="maintenance_invoice",
        entity_id=inv.public_id,
        actor_user_id=actor,
        company_id=company_id,
        after={"center": center.name, "number": inv.number, "total": total, "flags": flags},
    )
    return inv


def portal_invoice(db: Session, *, user_id: int, data: dict) -> dict:
    center = center_of(db, user_id)
    if not data.get("request_id"):
        raise AppError(422, "invoice_request_required")
    r = _for_center(db, data["request_id"], center, lock=True)
    if r.status not in INVOICE_FROM:
        raise AppError(409, "invoice_too_early", status=r.status)
    inv = _new_invoice(db, center=center, r=r, company_id=r.company_id, data=data, actor=user_id, own_file=True)
    db.commit()
    return _invoices_out(db, [inv])[0]


def office_invoice(db: Session, *, actor_user_id: int, data: dict, all_companies: bool, company_ids) -> dict:
    center = _center(db, data["center_id"])
    r = None
    if data.get("request_id"):
        r = _get(db, data["request_id"], lock=True, all_companies=all_companies, company_ids=company_ids)
        if r.center_id != center.id:
            raise AppError(409, "request_other_center")
        company_id = r.company_id
    else:
        company_id = data.get("company_id")
        if company_id is None:
            raise AppError(422, "field_required", field="company_id")
        if not org.company_ids_exist(db, [company_id]):
            raise AppError(422, "company_not_found")
        if not (all_companies or company_id in set(company_ids)):
            raise AppError(403, "company_out_of_scope")
    inv = _new_invoice(db, center=center, r=r, company_id=company_id, data=data, actor=actor_user_id, own_file=False)
    db.commit()
    return _invoices_out(db, [inv])[0]


def _invoice(db: Session, public_id, *, lock=False, all_companies: bool, company_ids) -> Invoice:
    q = _scoped(select(Invoice).where(Invoice.public_id == public_id), all_companies, company_ids, Invoice.company_id)
    inv = db.scalar(q.with_for_update() if lock else q)
    if inv is None:
        raise AppError(404, "invoice_not_found")
    return inv


def list_invoices(
    db: Session,
    *,
    status: str | None = None,
    payment_status: str | None = None,
    center_public_id=None,
    limit: int = 100,
    offset: int = 0,
    all_companies: bool,
    company_ids,
) -> list[dict]:
    q = _scoped(select(Invoice), all_companies, company_ids, Invoice.company_id)
    if status:
        q = q.where(Invoice.status == status)
    if payment_status:
        q = q.where(Invoice.payment_status == payment_status)
    if center_public_id:
        q = q.where(Invoice.center_id == _center(db, center_public_id).id)
    rows = db.scalars(q.order_by(Invoice.created_at.desc(), Invoice.id.desc()).limit(min(limit, 500)).offset(offset))
    return _invoices_out(db, list(rows))


def portal_invoices(db: Session, *, user_id: int, limit: int = 100) -> list[dict]:
    center = center_of(db, user_id)
    rows = db.scalars(
        select(Invoice).where(Invoice.center_id == center.id).order_by(Invoice.created_at.desc()).limit(min(limit, 300))
    )
    return _invoices_out(db, list(rows))


def decide_invoice(db: Session, public_id, *, approve: bool, reason: str | None, actor_user_id: int, **scope) -> dict:
    """Checked against the attached file by finance (BRD FR-INV-02); approval may close the request."""
    inv = _invoice(db, public_id, lock=True, **scope)
    if inv.status != "pending":
        raise AppError(409, "invoice_not_pending")
    if not approve and not reason:
        raise AppError(422, "reason_required")
    if not approvals.gate(
        db, "maintenance_invoice", **_invoice_approval(inv), actor_user_id=actor_user_id, approve=approve, reason=reason
    ):
        db.commit()  # this step recorded; the invoice waits for the next one
        return _invoices_out(db, [inv])[0]
    r = db.scalar(select(Request).where(Request.id == inv.request_id).with_for_update()) if inv.request_id else None
    inv.status = "approved" if approve else "rejected"
    inv.decided_by, inv.decided_at, inv.reason = actor_user_id, utcnow(), reason
    inv.version += 1
    db.flush()
    for key in ("mnt_invoice", "mnt_invoice_dup", "mnt_invoice_diff"):
        notifications.resolve(db, f"{key}:{inv.id}")
    if r is not None:
        _maybe_close(db, r, actor_user_id)
    audit.record(
        db,
        action="maintenance.invoice_approved" if approve else "maintenance.invoice_rejected",
        entity_type="maintenance_invoice",
        entity_id=inv.public_id,
        actor_user_id=actor_user_id,
        company_id=inv.company_id,
        after={"number": inv.number, "total": inv.total, "reason": reason},
    )
    if approve:
        emit(
            db,
            "maintenance.invoice.approved",
            inv.public_id,
            {
                "invoice_id": str(inv.public_id),
                "company_id": inv.company_id,
                "center_id": inv.center_id,
                "total": str(inv.total),
                "request_id": str(r.public_id) if r else None,
            },
        )
    db.commit()
    return _invoices_out(db, [inv])[0]


def mark_paid(db: Session, public_id, *, payment_ref: str | None, actor_user_id: int, **scope) -> dict:
    inv = _invoice(db, public_id, lock=True, **scope)
    if inv.status != "approved" or inv.payment_status == "paid":
        raise AppError(409, "invoice_not_payable")
    inv.payment_status, inv.paid_at, inv.paid_by, inv.payment_ref = "paid", utcnow(), actor_user_id, payment_ref
    inv.version += 1
    audit.record(
        db,
        action="maintenance.invoice_paid",
        entity_type="maintenance_invoice",
        entity_id=inv.public_id,
        actor_user_id=actor_user_id,
        company_id=inv.company_id,
        after={"number": inv.number, "total": inv.total, "payment_ref": payment_ref},
    )
    db.commit()
    return _invoices_out(db, [inv])[0]


def invoice_file(db: Session, public_id, **scope) -> files.FileInfo:
    return files.get(db, _invoice(db, public_id, **scope).file_sha256)


def portal_invoice_file(db: Session, public_id, *, user_id: int) -> files.FileInfo:
    center = center_of(db, user_id)
    inv = db.scalar(select(Invoice).where(Invoice.public_id == public_id, Invoice.center_id == center.id))
    if inv is None:
        raise AppError(404, "invoice_not_found")
    return files.get(db, inv.file_sha256)


# ------------------------------------------------------------------ for other modules


def counts(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> dict:
    """Dashboard (BRD FR-DSH-05): waiting for approval, under repair, ready for pickup."""
    rows = dict(
        db.execute(
            _scoped(select(Request.status, func.count()), all_companies, company_ids).group_by(Request.status)
        ).all()
    )
    return {
        "pending_approval": rows.get("requested", 0) + rows.get("quote_pending", 0),
        "under_repair": sum(rows.get(s, 0) for s in UNDER_REPAIR),
        "ready": rows.get("ready", 0),
        "referred": rows.get("referred", 0),
    }


# ------------------------------------------------------------------ for the accidents module


def center_brief(db: Session, public_id) -> dict:
    """A center the maintenance manager picks for a damage estimate: it must exist and be active."""
    c = _center(db, public_id)
    if not c.is_active:
        raise AppError(409, "center_inactive")
    return {"id": c.id, "public_id": str(c.public_id), "name": c.name}


def centers_brief(db: Session, ids: Iterable[int]) -> dict[int, dict]:
    ids = set(ids)
    if not ids:
        return {}
    return {c.id: _center_ref(c) for c in db.scalars(select(Center).where(Center.id.in_(ids)))}


def portal_center_id(db: Session, user_id: int) -> int:
    """The center of a portal account (403 for anyone else, or an inactive center)."""
    return center_of(db, user_id).id


def accident_repair(
    db: Session,
    *,
    vehicle_id: int,
    company_id: int,
    driver_id: int | None,
    center_id: int,
    description: str,
    amount: Decimal,
    items: list[dict],
    estimate_by: int,
    approved_by: int,
) -> int:
    """The repair of an accident, at the center that estimated the damage: a request already approved and referred,
    whose approved quote is the estimate (the center does not quote again; the repair starts at reception, and the
    invoice is compared with the estimate). In the caller's transaction; returns the request's id."""
    r = Request(
        vehicle_id=vehicle_id,
        company_id=company_id,
        driver_id=driver_id,
        kind="bodywork",
        description=description,
        created_by_user=approved_by,
        decided_by=approved_by,
        decided_at=utcnow(),
        center_id=center_id,
        referred_by=approved_by,
        referred_at=utcnow(),
        status="referred",
    )
    db.add(r)
    _flush(db, REQUEST_ERRORS)  # a vehicle is at one center at a time
    db.refresh(r)
    center = db.get(Center, center_id)
    for status, note in (("requested", ":accident"), ("approved", ":accident"), ("referred", center.name)):
        db.add(RequestEvent(request_id=r.id, status=status, by_user=approved_by, note=note))
    db.add(
        Quote(
            request_id=r.id,
            amount=amount,
            items=items,
            status="approved",
            created_by=estimate_by,
            decided_by=approved_by,
            decided_at=utcnow(),
        )
    )
    _audit(db, "maintenance.requested", r, actor_user_id=approved_by, after={"accident": True})
    _emit(db, "maintenance.request.referred", r, center_id=str(center.public_id))
    return r.id


def repair_summary(db: Session, request_id: int | None) -> dict | None:
    """Where the accident's repair stands and what it actually cost: its approved invoices (BRD FR-ACC-08)."""
    if request_id is None:
        return None
    r = db.get(Request, request_id)
    invoices = list(db.scalars(select(Invoice).where(Invoice.request_id == r.id, Invoice.status != "rejected")))
    approved = [i.total for i in invoices if i.status == "approved"]
    return {
        "id": str(r.public_id),
        "number": r.number,
        "status": r.status,
        "actual_cost": sum(approved, Decimal(0)) if approved else None,
        "invoices_pending": sum(1 for i in invoices if i.status == "pending"),
        "picked_up_at": r.picked_up_at,
    }


# ------------------------------------------------------------------ for finance


def center_names(db: Session, center_ids) -> dict[int, dict]:
    ids = list(set(center_ids))
    if not ids:
        return {}
    rows = db.execute(select(Center.id, Center.public_id, Center.name).where(Center.id.in_(ids)))
    return {i: {"type": "center", "id": str(p), "name": {"ar": n, "en": n}} for i, p, n in rows}


def invoice_centers(db: Session, invoice_ids) -> dict[int, dict]:
    """The center of each invoice, for finance's account statements."""
    ids = list(set(invoice_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(Invoice.id, Center.public_id, Center.name)
        .join(Center, Center.id == Invoice.center_id)
        .where(Invoice.id.in_(ids))
    )
    return {i: {"type": "center", "id": str(p), "name": {"ar": n, "en": n}} for i, p, n in rows}


def invoices_for_posting(db: Session, first, last) -> dict[str, list[dict]]:
    """Invoices approved, and invoices paid, on Kuwait days first..last: finance enters each once."""
    approved_on = func.date(func.timezone("Asia/Kuwait", Invoice.decided_at))
    paid_on = func.date(func.timezone("Asia/Kuwait", Invoice.paid_at))
    base = select(Invoice, Center.name).join(Center, Center.id == Invoice.center_id)
    approved = db.execute(
        base.add_columns(approved_on).where(Invoice.status == "approved", approved_on.between(first, last))
    ).all()
    paid = db.execute(
        base.add_columns(paid_on).where(Invoice.payment_status == "paid", paid_on.between(first, last))
    ).all()

    def out(i: Invoice, center: str, day) -> dict:
        return {
            "id": i.id,
            "number": i.number,
            "center": center,
            "company_id": i.company_id,
            "total": i.total,
            "date": day,
            "payment_ref": i.payment_ref,
        }

    return {"approved": [out(*r) for r in approved], "paid": [out(*r) for r in paid]}


# ------------------------------------------------------------------ the follow-up: priority, responsible, expected date


def _resolve_late(db: Session, r: Request) -> None:
    """Ready, collected, cancelled or given a new date: its late and escalated alerts close."""
    notifications.resolve(db, f"mnt_late:{r.id}:", prefix=True)
    notifications.resolve(db, f"mnt_escalated:{r.id}:", prefix=True)


def _alert_late(db: Session, r: Request, settings) -> int:
    """Late (past its expected date, or a long stay with none): alerted once per date; past the expected date by
    the settings' days (at once when urgent), escalated to the approvers, once per date. In the caller's
    transaction; how many alerts it raised."""
    reason = _late(r, settings, today())
    if reason is None:
        return 0
    center = db.get(Center, r.center_id) if r.center_id else None
    since = r.expected_ready_on if reason == "expected" else business_date(r.received_at)
    params = _alert_params(db, r) | {"center": center.name if center else "", "date": since.isoformat()}
    key = r.expected_ready_on.isoformat() if r.expected_ready_on else "stay"
    raised = int(
        notifications.raise_alert(
            db,
            "maintenance_late" if reason == "expected" else "maintenance_long_stay",
            company_id=r.company_id,
            entity_type="maintenance_request",
            entity_id=r.public_id,
            params=params,
            dedupe_key=f"mnt_late:{r.id}:{key}",
            once=True,  # handled by hand while still true: not raised again for the same date/cycle
        )
    )
    if reason != "expected" or r.escalated_at is not None:
        return raised
    if (today() - r.expected_ready_on).days < settings.escalate_after_days and r.priority != "urgent":
        return raised
    r.escalated_at = utcnow()
    assignee = identity.user_names(db, [r.assignee_id]).get(r.assignee_id) if r.assignee_id else None
    notifications.raise_alert(
        db,
        "maintenance_escalated",
        company_id=r.company_id,
        entity_type="maintenance_request",
        entity_id=r.public_id,
        params=params | {"assignee": assignee or "—"},
        dedupe_key=f"mnt_escalated:{r.id}:{key}",
        once=True,  # handled by hand while still true: not raised again for the same date/cycle
    )
    _audit(db, "maintenance.escalated", r, actor_type="system", after={"expected_ready_on": r.expected_ready_on})
    return raised + 1


PLAN_FIELDS = ("priority", "assignee_id", "expected_ready_on")


def set_plan(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int, **scope) -> dict:
    """The office's follow-up of a request: its priority, the user who follows it, the date the repair is expected
    to be ready (the center may give it too). A new date reopens the late and escalation alerts for that date."""
    r = _get(db, public_id, lock=True, **scope)
    if r.version != version:
        raise AppError(409, "version_conflict")
    if r.status in FINISHED:
        raise AppError(409, "request_finished", status=r.status)
    before = {"priority": r.priority, "assignee_id": r.assignee_id, "expected_ready_on": r.expected_ready_on}
    if "priority" in changes:
        r.priority = changes["priority"] or "normal"
    if "assignee_id" in changes:
        wanted = changes["assignee_id"]
        r.assignee_id = identity.office_user(db, wanted, "maintenance.view") if wanted else None
    if "expected_ready_on" in changes and changes["expected_ready_on"] != r.expected_ready_on:
        _set_expected(db, r, changes["expected_ready_on"])
    r.version += 1
    after = {"priority": r.priority, "assignee_id": r.assignee_id, "expected_ready_on": r.expected_ready_on}
    _audit(db, "maintenance.planned", r, actor_user_id=actor_user_id, after=after | {"before": before})
    _alert_late(db, r, org.get_section(db, "maintenance"))  # an urgent request already late is escalated now
    db.commit()
    return _detail(db, r)


def _set_expected(db: Session, r: Request, expected: date | None) -> None:
    if expected is not None and expected < business_date(r.created_at):
        raise AppError(422, "expected_before_request")
    r.expected_ready_on, r.escalated_at = expected, None
    _resolve_late(db, r)


def portal_expected(db: Session, public_id, *, user_id: int, expected_ready_on: date, note: str | None) -> dict:
    """The center says when it expects the car to be ready (or a new date): the office follows it from there."""
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.status not in NOT_READY:
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    if expected_ready_on < today():
        raise AppError(422, "expected_in_past")
    if expected_ready_on != r.expected_ready_on:
        _set_expected(db, r, expected_ready_on)
        r.version += 1
        db.add(RequestEvent(request_id=r.id, status=r.status, by_user=user_id, note=note or ":expected_date"))
        _audit(db, "maintenance.expected", r, actor_user_id=user_id, after={"expected_ready_on": expected_ready_on})
    db.commit()
    return _detail(db, r, for_center=True)


def assignees(db: Session) -> list[dict]:
    """Who a request can be given to: the active office users who see maintenance."""
    return [{"id": u["id"], "name": u["name"]} for u in identity.users_with_permission(db, "maintenance.view")]


# ------------------------------------------------------------------ a replacement car while his own is at the center


def _open_replacement(db: Session, r: Request) -> tuple[int, dict] | None:
    """The replacement car the driver still holds for this request: (custody id, the custody as listed)."""
    ids = list(db.scalars(select(Replacement.custody_id).where(Replacement.request_id == r.id)))
    return next(((i, b) for i, b in fleet.custodies_brief(db, ids).items() if b["ended_at"] is None), None)


def give_replacement(db: Session, public_id, *, data: dict, actor_user_id: int, **scope) -> dict:
    """A replacement car for the driver while his own is at the center being repaired: a custody of its own kind,
    started with its reading and photo. His own car stays in his custody; the replacement ends when he collects his
    car (or when the office takes it back first). One at a time."""
    r = _get(db, public_id, lock=True, **scope)
    if r.status not in UNDER_REPAIR + ("quote_pending",):
        raise AppError(409, "replacement_not_at_center", status=r.status)
    if _open_replacement(db, r) is not None:
        raise AppError(409, "driver_has_replacement")
    custody = fleet.start_replacement(
        db,
        own_vehicle_id=r.vehicle_id,
        vehicle_public_id=data["vehicle_id"],
        odometer_km=data["odometer_km"],
        photo_sha256=data["photo_sha256"],
        photos=data.get("photos"),
        started_at=data.get("started_at"),
        actor_user_id=actor_user_id,
        **scope,
    )
    db.add(Replacement(custody_id=custody.id, request_id=r.id, created_by=actor_user_id))
    plate = fleet.plate_numbers(db, [custody.vehicle_id]).get(custody.vehicle_id, "")
    r.version += 1
    db.add(RequestEvent(request_id=r.id, status=r.status, by_user=actor_user_id, note=f":replacement_given {plate}"))
    _audit(db, "maintenance.replacement_given", r, actor_user_id=actor_user_id, after={"plate": plate})
    db.commit()
    return _detail(db, r)


def return_replacement(db: Session, public_id, *, data: dict, actor_user_id: int, **scope) -> dict:
    """The office takes the replacement car back before the driver collects his own (its reading and photo)."""
    r = _get(db, public_id, lock=True, **scope)
    held = _open_replacement(db, r)
    if held is None:
        raise AppError(409, "no_replacement")
    _end_replacement(
        db,
        r,
        held,
        odometer_km=data["odometer_km"],
        photo_sha256=data["photo_sha256"],
        at=data.get("ended_at"),
        actor_user_id=actor_user_id,
        photos=data.get("photos"),
    )
    db.commit()
    return _detail(db, r)


def _end_replacement(
    db: Session, r: Request, held: tuple[int, dict], *, actor_user_id=None, device_id=None, **reading
) -> None:
    custody_id, brief = held
    fleet.end_replacement(db, custody_id, actor_user_id=actor_user_id, device_id=device_id, **reading)
    plate = brief["vehicle"]["plate_number"]
    r.version += 1
    db.add(
        RequestEvent(
            request_id=r.id,
            status=r.status,
            by_user=actor_user_id,
            by_device=device_id,
            note=f":replacement_returned {plate}",
        )
    )
    _audit(
        db,
        "maintenance.replacement_returned",
        r,
        actor_user_id=actor_user_id,
        actor_type="device" if device_id is not None else None,
        after={"plate": plate, "odometer_km": reading["odometer_km"]},
    )


# ------------------------------------------------------------------ periodic schedules (by date and by distance)


def _schedule(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Schedule:
    q = _scoped(
        select(Schedule).where(Schedule.public_id == public_id), all_companies, company_ids, Schedule.company_id
    )
    found = db.scalar(q.with_for_update() if lock else q)
    if found is None:
        raise AppError(404, "schedule_not_found")
    return found


def _worst(states: list[str]) -> str:
    for s in ("overdue", "due", "ok"):
        if s in states:
            return s
    return "unknown"


def _schedules_out(db: Session, rows: list[Schedule]) -> list[dict]:
    """Each schedule with when it falls due (date, reading) and its state now: ok, due (soon), overdue, or unknown
    when only the distance counts and the reading it needs is missing (never a guess)."""
    if not rows:
        return []
    settings = org.get_section(db, "maintenance")
    day, now = today(), utcnow()
    cards = fleet.vehicle_cards(db, {s.vehicle_id for s in rows})
    readings = fleet.last_readings(db, {s.vehicle_id for s in rows})
    open_requests = {
        sid: {"id": str(p), "number": n, "status": st}
        for sid, p, n, st in db.execute(
            select(Request.schedule_id, Request.public_id, Request.number, Request.status).where(
                Request.schedule_id.in_([s.id for s in rows]), Request.status.notin_(FINISHED)
            )
        )
    }
    out = []
    for s in rows:
        reading = readings.get(s.vehicle_id)
        states, days_left, km_left = [], None, None
        due_on = s.last_done_on + timedelta(days=s.every_days) if s.every_days else None
        if due_on is not None:
            days_left = (due_on - day).days
            states.append("overdue" if days_left < 0 else "due" if days_left <= settings.due_soon_days else "ok")
        due_km = s.last_done_km + s.every_km if s.every_km and s.last_done_km is not None else None
        km_state = None
        if s.every_km:
            if due_km is None:
                km_state = "no_baseline"  # the reading when it was last done is unknown
            elif reading is None:
                km_state = "no_reading"  # the car was never read
            else:
                km_left = due_km - reading["km"]
                km_state = "overdue" if km_left <= 0 else "due" if km_left <= settings.due_soon_km else "ok"
                states.append(km_state)
        out.append(
            {
                "id": str(s.public_id),
                "vehicle": cards.get(s.vehicle_id, {}),
                "company_id": s.company_id,
                "kind": s.kind,
                "title": s.title,
                "every_days": s.every_days,
                "every_km": s.every_km,
                "last_done_on": s.last_done_on,
                "last_done_km": s.last_done_km,
                "due_on": due_on,
                "due_km": due_km,
                "days_left": days_left,
                "km_left": km_left,
                "current_km": reading["km"] if reading else None,
                "current_km_at": reading["at"] if reading else None,
                "reading_stale": reading is not None and now - reading["at"] > READING_STALE,
                "km_state": km_state,
                "state": _worst(states) if s.active else "inactive",
                "open_request": open_requests.get(s.id),
                "active": s.active,
                "notes": s.notes,
                "version": s.version,
            }
        )
    return out


def list_schedules(
    db: Session, *, vehicle_public_id=None, state: str | None = None, active: bool = True, **scope
) -> list[dict]:
    q = _scoped(select(Schedule), scope["all_companies"], scope["company_ids"], Schedule.company_id)
    if vehicle_public_id:
        q = q.where(Schedule.vehicle_id == fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id)
    if active:
        q = q.where(Schedule.active.is_(True))
    rows = _schedules_out(db, list(db.scalars(q.order_by(Schedule.vehicle_id, Schedule.id))))
    if state:
        wanted = set(state.split(","))
        rows = [x for x in rows if x["state"] in wanted]
    order = {"overdue": 0, "due": 1, "unknown": 2, "ok": 3, "inactive": 4}
    return sorted(rows, key=lambda x: (order[x["state"]], x["due_on"] or date.max, x["km_left"] or 0))


def get_schedule(db: Session, public_id, **scope) -> dict:
    return _schedules_out(db, [_schedule(db, public_id, **scope)])[0]


def create_schedule(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    """Every so many days and/or kilometres since it was last done. The last time it was done is given, or today at
    the car's last reading (counting from now). With no reading at all, the distance waits for one (unknown)."""
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope)
    if not data.get("every_days") and not data.get("every_km"):
        raise AppError(422, "schedule_interval_required")
    done_on = data.get("last_done_on") or today()
    if done_on > today():
        raise AppError(422, "time_in_future")
    done_km = data.get("last_done_km")
    if done_km is None and data.get("every_km"):
        reading = fleet.last_readings(db, [vehicle.id]).get(vehicle.id)
        done_km = reading["km"] if reading else None
    s = Schedule(
        vehicle_id=vehicle.id,
        company_id=vehicle.company_id,
        kind=data.get("kind") or "periodic",
        title=data["title"],
        every_days=data.get("every_days"),
        every_km=data.get("every_km"),
        last_done_on=done_on,
        last_done_km=done_km,
        notes=data.get("notes"),
        created_by=actor_user_id,
    )
    db.add(s)
    _flush(db, SCHEDULE_ERRORS)
    db.refresh(s)
    out = _schedules_out(db, [s])[0]
    audit.record(
        db,
        action="maintenance.schedule_created",
        entity_type="maintenance_schedule",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        company_id=s.company_id,
        after={k: out[k] for k in ("title", "every_days", "every_km", "last_done_on", "last_done_km")},
    )
    db.commit()
    return out


SCHEDULE_FIELDS = ("kind", "title", "every_days", "every_km", "notes", "active")


def update_schedule(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int, **scope) -> dict:
    s = _schedule(db, public_id, lock=True, **scope)
    if s.version != version:
        raise AppError(409, "version_conflict")
    before = {f: getattr(s, f) for f in SCHEDULE_FIELDS}
    for field in SCHEDULE_FIELDS:
        if field in changes and not (field in ("title", "kind", "active") and changes[field] is None):
            setattr(s, field, changes[field])
    if not s.every_days and not s.every_km:
        raise AppError(422, "schedule_interval_required")
    s.version += 1
    s.updated_at = func.now()
    _flush(db, SCHEDULE_ERRORS)
    _resolve_due(db, s)  # the next scan alerts again by the new terms
    audit.record(
        db,
        action="maintenance.schedule_updated",
        entity_type="maintenance_schedule",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        company_id=s.company_id,
        before=before,
        after={f: getattr(s, f) for f in SCHEDULE_FIELDS},
    )
    db.commit()
    db.refresh(s)
    return _schedules_out(db, [s])[0]


def _resolve_due(db: Session, s: Schedule) -> None:
    notifications.resolve(db, f"mnt_due:{s.id}:", prefix=True)
    notifications.resolve(db, f"mnt_overdue:{s.id}:", prefix=True)


def _mark_done(
    db: Session, s: Schedule, *, on: date, km: int | None, actor_user_id: int | None, request: Request | None = None
) -> bool:
    """Done on that day at that reading: the next one counts from there. Never moves back in time or distance (a
    late record of an older service changes nothing)."""
    if on < s.last_done_on or (km is not None and s.last_done_km is not None and km < s.last_done_km):
        return False
    before = {"last_done_on": s.last_done_on, "last_done_km": s.last_done_km}
    s.last_done_on, s.last_done_km = on, km if km is not None else s.last_done_km
    s.version += 1
    s.updated_at = func.now()
    _resolve_due(db, s)
    audit.record(
        db,
        action="maintenance.schedule_done",
        entity_type="maintenance_schedule",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        actor_type=None if actor_user_id else "system",
        company_id=s.company_id,
        before=before,
        after={"last_done_on": on, "last_done_km": s.last_done_km} | ({"request": request.number} if request else {}),
    )
    return True


def schedule_done(
    db: Session, public_id, *, done_on: date, done_km: int | None, note: str | None, actor_user_id: int, **scope
) -> dict:
    """Recorded by hand: done outside a request in the system (another workshop, the company's own)."""
    s = _schedule(db, public_id, lock=True, **scope)
    if done_on > today():
        raise AppError(422, "time_in_future")
    if not _mark_done(db, s, on=done_on, km=done_km, actor_user_id=actor_user_id):
        raise AppError(422, "schedule_done_before_last")
    if note:
        s.notes = note
    db.commit()
    db.refresh(s)
    return _schedules_out(db, [s])[0]


def _schedule_from_pickup(db: Session, r: Request, at: datetime) -> None:
    """The request carried out its schedule: done on the pickup day, at the reading the car left the center with."""
    if r.schedule_id is None:
        return
    s = db.scalar(select(Schedule).where(Schedule.id == r.schedule_id).with_for_update())
    reading = fleet.last_readings(db, [r.vehicle_id]).get(r.vehicle_id)
    _mark_done(db, s, on=business_date(at), km=reading["km"] if reading else r.final_km, actor_user_id=None, request=r)


def _due_text(x: dict) -> dict:
    ar, en = [], []
    if x["due_on"] is not None:
        ar.append(f"تاريخ {x['due_on'].isoformat()}")
        en.append(f"date {x['due_on'].isoformat()}")
    if x["due_km"] is not None:
        ar.append(f"عداد {x['due_km']:,} كم")
        en.append(f"odometer {x['due_km']:,} km")
    return {"ar": " أو ".join(ar) or "—", "en": " or ".join(en) or "—"}


def scan_due(db: Session) -> int:
    """Daily: schedules due soon or overdue (none while a request carries them out), and requests late or staying
    long at the center (escalated as the settings say). Each alert once per situation; it closes by itself when the
    schedule is done or the car is ready."""
    settings = org.get_section(db, "maintenance")
    raised = 0
    for x in list_schedules(db, all_companies=True, company_ids=()):
        if x["state"] not in ("due", "overdue") or x["open_request"] is not None:
            continue
        s = db.scalar(select(Schedule).where(Schedule.public_id == x["id"]))
        cycle = f"{s.id}:{s.last_done_on.isoformat()}:{s.last_done_km}"
        if x["state"] == "overdue":
            notifications.resolve(db, f"mnt_due:{cycle}")
        raised += notifications.raise_alert(
            db,
            "maintenance_overdue" if x["state"] == "overdue" else "maintenance_due",
            company_id=s.company_id,
            entity_type="maintenance_schedule",
            entity_id=s.public_id,
            params={"plate": x["vehicle"].get("plate_number", ""), "title": s.title, "due": _due_text(x)},
            dedupe_key=f"mnt_{x['state']}:{cycle}",
            once=True,  # handled by hand while still true: not raised again for the same date/cycle
        )
    for r in db.scalars(select(Request).where(Request.status.in_(NOT_READY)).with_for_update()):
        raised += _alert_late(db, r, settings)
    db.commit()
    return raised
