"""Maintenance requests, maintenance centers and their portal, repair quotes and invoices (BRD 5.9, 5.10).

Who does what: a driver (from the app) or the office asks; a supervisor or the maintenance manager approves (an
emergency is approved at once and reviewed afterwards) and refers the vehicle to a center; the center works in its
portal: reception (the custody ends there, with the center's odometer reading and photo, so tracking stops and the
vehicle is "in maintenance"), inspection, a quote (approved automatically up to the approval limit in the settings,
otherwise by the manager before the repair starts), repair, completion (final odometer with its photo), ready for
pickup. Picked up, the vehicle is available again; the request closes once its invoice is approved (configurable).

Straight to the center (settings, maintenance.direct_to_center): the driver picks the center in the app and the
request reaches it at once, already referred, with no office approval; the center may repair without a quote (a quote
it sends still follows the limit), uploads its invoice before calling the driver, and the driver confirms the pickup
in the app with the odometer, which gives him the vehicle back. The office follows, may change the center or cancel
before the reception, and finance approves and pays the center's invoices as before.

Center accounts see only what was referred to their center: every portal function takes the user and resolves the
center itself. Every status change is a row in request_events: the timeline, who decided, and the time spent at the
center and in each status.
"""

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
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
    Request,
    RequestEvent,
    RequestPhoto,
)
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

CENTER_ERRORS = {"centers_name_idx": "center_name_taken"}
REQUEST_ERRORS = {"requests_one_at_center_idx": "vehicle_at_center", "requests_client_ref_key": "request_exists"}
CANCELLABLE = ("requested", "approved", "referred")
QUOTE_FROM = ("received", "inspection", "in_repair", "waiting_parts")
INVOICE_FROM = ("completed", "ready", "picked_up")
PORTAL_MOVES = {"inspection": ("received",), "in_repair": ("waiting_parts",), "waiting_parts": ("in_repair",)}
HISTORY = ("picked_up", "closed", "cancelled")
UNDER_REPAIR = ("received", "inspection", "in_repair", "waiting_parts", "completed")
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


def _direct(db: Session) -> bool:
    """Requests go from the driver straight to the center he picks (the settings)."""
    return org.get_section(db, "maintenance").direct_to_center


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


def _requests_out(db: Session, rows: list[Request], *, for_center: bool = False) -> list[dict]:
    cards = fleet.vehicle_cards(db, {r.vehicle_id for r in rows})
    names = {} if for_center else people.names(db, {r.driver_id for r in rows if r.driver_id})
    center_ids = {r.center_id for r in rows if r.center_id}
    centers = {c.id: c for c in db.scalars(select(Center).where(Center.id.in_(center_ids)))} if center_ids else {}
    now = utcnow()
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
        end = events[i + 1].at if i + 1 < len(events) else None
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
    return out | {
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


def create_request(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope)
    _check_images(db, data.get("photos") or [])
    r = Request(
        vehicle_id=vehicle.id,
        company_id=vehicle.company_id,
        driver_id=fleet.holder(db, vehicle.id),
        kind=data["kind"],
        description=data["description"],
        odometer_km=data.get("odometer_km"),
        emergency=data.get("emergency", False),
        created_by_user=actor_user_id,
    )
    db.add(r)
    db.flush()
    db.refresh(r)
    db.add(RequestEvent(request_id=r.id, status="requested", by_user=actor_user_id))
    _add_photos(db, r, "request", data.get("photos") or [])
    params = _alert_params(db, r)
    if r.emergency:  # repaired first, approved afterwards (BRD FR-MNT-02)
        r.decided_at = utcnow()
        _event(db, r, "approved", by_user=actor_user_id, note=":emergency")
        notifications.raise_alert(
            db,
            "maintenance_emergency",
            company_id=r.company_id,
            entity_type="maintenance_request",
            entity_id=r.public_id,
            params=params,
            dedupe_key=f"mnt_emergency:{r.id}",
        )
    else:
        notifications.raise_alert(
            db,
            "maintenance_requested",
            company_id=r.company_id,
            entity_type="maintenance_request",
            entity_id=r.public_id,
            params=params,
            dedupe_key=f"mnt_request:{r.id}",
        )
        approvals.submitted(db, "maintenance_request", **_approval(db, r), actor_user_id=actor_user_id)
    _audit(db, "maintenance.requested", r, actor_user_id=actor_user_id, after={"emergency": r.emergency})
    _emit(db, "maintenance.request.created", r, vehicle_id=str(vehicle.public_id), emergency=r.emergency)
    db.commit()
    return _detail(db, r)


def driver_request(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    """From the app, for the vehicle the driver holds now; photos from this phone's camera only."""
    if db.scalar(select(Request.id).where(Request.client_ref == data["client_ref"])):
        raise AppError(409, "request_exists")  # a retry: already recorded
    custody = fleet.open_custody_for_driver(db, employee_id)
    if custody is None:
        raise AppError(409, "no_vehicle_in_custody")
    _check_images(db, data.get("photos") or [], device_id=device_id)
    # straight to the center he picked; an app that sends no center (an older one) goes through the office, and so
    # does a vehicle in an accident (its repair follows the accident: estimate, approval, the office's center)
    center = None
    if data.get("center_id") and _direct(db):
        if fleet.vehicle_cards(db, [custody.vehicle_id])[custody.vehicle_id]["status"] != "accident":
            center = _center(db, data["center_id"])
            if center.id not in {c.id for c in _bookable(db)}:
                raise AppError(409, "center_inactive")
    now = utcnow()
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
    if center is not None:  # the database's rules for a request at a center: one per vehicle, a center set
        r.status, r.center_id, r.decided_at, r.referred_at, r.direct = "referred", center.id, now, now, True
    db.add(r)
    _flush(db, REQUEST_ERRORS)
    db.refresh(r)
    db.add(RequestEvent(request_id=r.id, status="requested", by_device=device_id))
    _add_photos(db, r, "request", data.get("photos") or [])
    if center is not None:
        db.add(RequestEvent(request_id=r.id, status="referred", by_device=device_id, note=center.name))
        _audit(db, "maintenance.requested", r, actor_type="device", after={"center": center.name})
        _emit(db, "maintenance.request.referred", r, center_id=str(center.public_id))
        db.commit()
        return for_driver(db, employee_id, only=r.id)[0]
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
    _audit(db, "maintenance.requested", r, actor_type="device")
    _emit(db, "maintenance.request.created", r, emergency=False)
    db.commit()
    return for_driver(db, employee_id, only=r.id)[0]


def for_driver(db: Session, employee_id: int, *, limit: int = 20, only: int | None = None) -> list[dict]:
    q = select(Request).where(Request.driver_id == employee_id)
    if only is not None:
        q = q.where(Request.id == only)
    rows = list(db.scalars(q.order_by(Request.created_at.desc(), Request.id.desc()).limit(limit)))
    plates = fleet.plate_numbers(db, {r.vehicle_id for r in rows})
    center_ids = {r.center_id for r in rows if r.center_id}
    centers = {c.id: c for c in db.scalars(select(Center).where(Center.id.in_(center_ids)))} if center_ids else {}
    return [
        {
            "id": str(r.public_id),
            "number": r.number,
            "vehicle_plate": plates.get(r.vehicle_id, ""),
            "kind": r.kind,
            "description": r.description,
            "status": r.status,
            "center": _center_ref(centers.get(r.center_id)),
            "created_at": r.created_at,
            "ready_at": r.ready_at,
            "picked_up_at": r.picked_up_at,
            "decision_note": r.decision_note if r.status == "rejected" else None,
            "direct": r.direct,  # he collects it himself in the app
        }
        for r in rows
    ]


def driver_form(db: Session) -> dict:
    """What the app's request form offers: in the direct mode, the active centers he may take the car to."""
    direct = _direct(db)
    centers = _bookable(db) if direct else []
    return {
        "direct_to_center": direct,
        "centers": [_center_ref(c) | {"specialty": c.specialty} for c in centers],
    }


def driver_picked_up(db: Session, public_id, *, employee_id: int, device_id: int, data: dict) -> dict:
    """Straight to the center: the driver collected his car, with his odometer reading and camera photo, and it is
    his again at once (no office handover). Otherwise the office or the center records the pickup."""
    r = db.scalar(
        select(Request).where(Request.public_id == public_id, Request.driver_id == employee_id).with_for_update()
    )
    if r is None:
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
    if not r.direct:
        raise AppError(409, "pickup_by_office")  # the office or the center records it and the office hands over
    _check_images(db, [data["odometer_photo"]], device_id=device_id)
    now = utcnow()
    at = data.get("picked_up_at") or now
    # when the photo was taken: after the car was ready, not in the future, and late by two days at most
    if at > now + fleet.CLOCK_SKEW or at < now - fleet.DRIVER_READING_DELAY or (r.ready_at and at < r.ready_at):
        raise AppError(422, "invalid_recorded_at")
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
    db.commit()
    return for_driver(db, employee_id, only=r.id)[0]


def list_requests(
    db: Session,
    *,
    status: str | None = None,
    active: bool | None = None,
    vehicle_public_id=None,
    center_public_id=None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Request), **scope)
    if status:
        q = q.where(Request.status.in_(status.split(",")))
    if active is True:
        q = q.where(Request.status.notin_(("rejected", "closed", "cancelled")))
    if vehicle_public_id:
        q = q.where(Request.vehicle_id == fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id)
    if center_public_id:
        q = q.where(Request.center_id == _center(db, center_public_id).id)
    rows = db.scalars(q.order_by(Request.created_at.desc(), Request.id.desc()).limit(min(limit, 500)).offset(offset))
    return _requests_out(db, list(rows))


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
    approvals.withdrawn(db, "maintenance_request", [r.id])
    notifications.resolve(db, f"mnt_request:{r.id}")
    _audit(db, "maintenance.cancelled", r, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _detail(db, r)


def picked_up(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    """The company collected the vehicle (recorded in the office)."""
    r = _get(db, public_id, lock=True, **scope)
    _picked_up(db, r, actor_user_id)
    db.commit()
    return _detail(db, r)


def _picked_up(
    db: Session, r: Request, actor_user_id: int | None = None, *, by_device: int | None = None, at=None
) -> None:
    if r.status != "ready":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    r.picked_up_at, r.picked_up_by = at or utcnow(), actor_user_id
    _event(db, r, "picked_up", by_user=actor_user_id, by_device=by_device, at=at)
    fleet.released_from_maintenance(db, r.vehicle_id)
    notifications.resolve(db, f"mnt_ready:{r.id}")
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
        "direct_to_center": _direct(db),  # the portal says how new requests arrive
    }


def receive(db: Session, public_id, *, user_id: int, data: dict) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.status != "referred":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    at = data.get("received_at") or utcnow()
    _check_images(db, [data["odometer_photo"], *(data.get("photos") or [])], user_id=user_id)
    ended = fleet.received_for_maintenance(
        db,
        r.vehicle_id,
        odometer_km=data["odometer_km"],
        photo_sha256=data["odometer_photo"],
        at=at,
        actor_user_id=user_id,
    )
    r.received_at, r.received_by, r.received_km = at, user_id, data["odometer_km"]
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
        after={"odometer_km": data["odometer_km"], "custody_ended": bool(ended)},
    )
    _emit(db, "maintenance.vehicle.received", r, center_id=str(center.public_id))
    db.commit()
    return _detail(db, r, for_center=True)


def set_status(db: Session, public_id, *, user_id: int, status: str, note: str | None) -> dict:
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
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


def ready(db: Session, public_id, *, user_id: int, note: str | None) -> dict:
    """Ready for pickup: the office is alerted and the driver sees it in the app (BRD FR-MNT-10)."""
    center = center_of(db, user_id)
    r = _for_center(db, public_id, center, lock=True)
    if r.status != "completed":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    if r.direct and not db.scalar(
        select(Invoice.id).where(Invoice.request_id == r.id, Invoice.status != "rejected").limit(1)
    ):
        raise AppError(409, "invoice_required")  # the invoice first, then the driver is called
    r.ready_at = utcnow()
    _event(db, r, "ready", by_user=user_id, note=note)
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
