"""Maintenance requests, maintenance centers and their portal, repair quotes and invoices (BRD 5.9, 5.10).

Who does what: a driver (from the app) or the office asks; a supervisor or the maintenance manager approves (an
emergency is approved at once and reviewed afterwards) and refers the vehicle to a center; the center works in its
portal: reception (the custody ends there, with the center's odometer reading and photo, so tracking stops and the
vehicle is "in maintenance"), inspection, a quote (approved automatically up to the approval limit in the settings,
otherwise by the manager before the repair starts), repair, completion (final odometer with its photo), ready for
pickup. Picked up, the vehicle is available again; the request closes once its invoice is approved (configurable).

Center accounts see only what was referred to their center: every portal function takes the user and resolves the
center itself. Every status change is a row in request_events: the timeline, who decided, and the time spent at the
center and in each status.
"""

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
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
    photos = db.scalars(select(RequestPhoto).where(RequestPhoto.request_id == r.id))
    return out | {
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
    _flush(db, REQUEST_ERRORS)
    db.refresh(r)
    db.add(RequestEvent(request_id=r.id, status="requested", by_device=device_id))
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
        }
        for r in rows
    ]


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
    r.decided_by, r.decided_at, r.decision_note = actor_user_id, utcnow(), note
    _event(db, r, "approved", by_user=actor_user_id, note=note)
    notifications.resolve(db, f"mnt_request:{r.id}")
    _audit(db, "maintenance.approved", r, actor_user_id=actor_user_id, after={"note": note})
    _emit(db, "maintenance.request.approved", r)
    db.commit()
    return _detail(db, r)


def reject(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    r = _get(db, public_id, lock=True, **scope)
    if r.status != "requested":
        raise AppError(409, "request_not_pending", status=r.status)
    r.decided_by, r.decided_at, r.decision_note = actor_user_id, utcnow(), reason
    _event(db, r, "rejected", by_user=actor_user_id, note=reason)
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


def _picked_up(db: Session, r: Request, actor_user_id: int) -> None:
    if r.status != "ready":
        raise AppError(409, "invalid_maintenance_status", status=r.status)
    r.picked_up_at, r.picked_up_by = utcnow(), actor_user_id
    _event(db, r, "picked_up", by_user=actor_user_id)
    fleet.released_from_maintenance(db, r.vehicle_id)
    notifications.resolve(db, f"mnt_ready:{r.id}")
    _audit(db, "maintenance.picked_up", r, actor_user_id=actor_user_id, after={"stay_seconds": _stay(r, utcnow())})
    _emit(db, "maintenance.vehicle.picked_up", r)
    _maybe_close(db, r, actor_user_id)


def _maybe_close(db: Session, r: Request, actor_user_id: int) -> None:
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
    return {"id": str(c.public_id), "name": c.name, "phone": c.phone, "address": c.address}


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
    # only the way back from waiting for parts
    if r.status not in PORTAL_MOVES[status]:
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
    if r.status not in ("in_repair", "waiting_parts"):
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
