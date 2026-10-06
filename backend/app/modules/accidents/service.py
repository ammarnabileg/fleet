"""Accidents (BRD 5.11, UAT-24..26).

Reported from the app (the vehicle the driver held at that moment, time and place from the phone, camera photos from
several angles) or by the office; the responsible driver is whoever held the vehicle at the accident time, from the
custody log. The vehicle becomes "in an accident". The police report may come with the report or later: until then
the accident waits for it (and alerts after the days set in the settings), and no liability outcome can be recorded
without it (UAT-24; the database refuses it too).

The maintenance manager refers the accident to a center, which enters its damage estimate item by item in its portal;
the manager approves it (or rejects it with a reason: the center estimates again, or another center is chosen). The
outcome (no liability, driver, shared) is approved by the holder of accidents.approve: when the driver is liable, a
deduction is created for the driver, the approved damage in full or by the liability percentage, in monthly
installments that payroll applies and the driver sees in the app (UAT-26). The repair goes to the same center as a
maintenance request whose approved quote is the estimate; its approved invoices are the actual cost, compared with
the estimate (FR-ACC-08).

Every step is a row in accident_events: the timeline and who did what.
"""

from collections.abc import Iterable
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.accidents.models import Accident, AccidentEvent, AccidentPhoto
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.maintenance import service as maintenance
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.payroll import service as payroll
from app.modules.people import service as people

ERRORS = {"accidents_client_ref_key": "accident_exists"}
CLOCK_SKEW = timedelta(minutes=5)
DRIVER_DELAY = timedelta(hours=48)  # the app may be offline; older accidents are reported by the office
OFFICE_BACKDATE = timedelta(days=365)
CENT = Decimal("0.001")
ALERTS = ("acc_reported", "acc_police", "acc_estimate")


# ------------------------------------------------------------------ helpers


def _event(db: Session, a: Accident, kind: str, *, by_user=None, by_device=None, note=None) -> None:
    """A note starting with ":" is a code the screens translate; any other note is a person's."""
    a.version += 1
    db.add(AccidentEvent(accident_id=a.id, kind=kind, by_user=by_user, by_device=by_device, note=note))


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Accident.company_id.in_(list(company_ids)))


def _get(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Accident:
    q = _scoped(select(Accident).where(Accident.public_id == public_id), all_companies, company_ids)
    a = db.scalar(q.with_for_update() if lock else q)
    if a is None:
        raise AppError(404, "accident_not_found")
    return a


def _open(a: Accident) -> None:
    if a.status != "open":
        raise AppError(409, "accident_not_open", status=a.status)


def _check_time(at: datetime, oldest: timedelta) -> None:
    now = utcnow()
    if at > now + CLOCK_SKEW:
        raise AppError(422, "time_in_future")
    if at < now - oldest:
        raise AppError(422, "time_too_old")


def _check_images(db: Session, shas: Iterable[str], *, user_id: int | None = None, device_id: int | None = None):
    """Images uploaded by the same account (a center user) or taken by the same phone's camera."""
    for sha in dict.fromkeys(shas):
        info = files.get(db, sha)
        if info.content_type not in files.IMAGES:
            raise AppError(422, "photo_must_be_image")
        if device_id is not None and (info.uploaded_by_device != device_id or info.source != "camera"):
            raise AppError(422, "file_not_yours")
        if user_id is not None and info.uploaded_by_user != user_id:
            raise AppError(422, "file_uploaded_by_other_account")


def _check_document(db: Session, sha: str, *, user_id: int | None = None) -> None:
    info = files.get(db, sha)  # an image or a PDF
    if user_id is not None and info.uploaded_by_user != user_id:
        raise AppError(422, "file_uploaded_by_other_account")


def _add_photos(db: Session, a: Accident, shas: Iterable[str]) -> None:
    existing = set(db.scalars(select(AccidentPhoto.file_sha256).where(AccidentPhoto.accident_id == a.id)))
    for sha in dict.fromkeys(shas):
        if sha not in existing:
            db.add(AccidentPhoto(accident_id=a.id, file_sha256=sha))


def _items(raw: list[dict]) -> list[dict]:
    return [i | {"amount": (Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"]))).quantize(CENT)} for i in raw]


def _items_total(items: list[dict]) -> Decimal:
    return sum((Decimal(str(i["quantity"])) * Decimal(str(i["unit_price"])) for i in items), Decimal(0)).quantize(CENT)


def _alert_params(db: Session, a: Accident) -> dict:
    return {"plate": fleet.plate_numbers(db, [a.vehicle_id]).get(a.vehicle_id, ""), "number": a.number}


def _resolve_all(db: Session, a: Accident) -> None:
    for prefix in ALERTS:
        notifications.resolve(db, f"{prefix}:{a.id}")


def _audit(db: Session, action: str, a: Accident, *, actor_user_id=None, actor_type=None, after=None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="accident",
        entity_id=a.public_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        company_id=a.company_id,
        after={"number": a.number} | (after or {}),
    )


def _emit(db: Session, event_type: str, a: Accident, **payload) -> None:
    emit(db, event_type, a.public_id, {"accident_id": str(a.public_id), "number": a.number} | payload)


def stage(a: Accident) -> str:
    """Where the accident stands, for the lists (the police report is a separate flag: it may come at any point
    before the outcome)."""
    if a.status != "open":
        return a.status
    if a.liability is not None:
        return "outcome_recorded"
    if a.estimate_status == "pending":
        return "estimate_pending"
    if a.estimate_status == "approved":
        return "awaiting_outcome"
    if a.estimate_status == "rejected":
        return "estimate_rejected"
    if a.center_id is not None:
        return "awaiting_estimate"
    return "reported"


# ------------------------------------------------------------------ output


def _out(db: Session, rows: list[Accident]) -> list[dict]:
    cards = fleet.vehicle_cards(db, {a.vehicle_id for a in rows})
    names = people.names(db, {a.driver_id for a in rows if a.driver_id})
    centers = maintenance.centers_brief(db, {a.center_id for a in rows if a.center_id})
    deductions = {a.id: payroll.deduction(db, a.deduction_id) for a in rows if a.deduction_id}
    return [
        {
            "id": str(a.public_id),
            "number": a.number,
            "vehicle": cards.get(a.vehicle_id, {}),
            "company_id": a.company_id,
            "driver": names.get(a.driver_id),
            "occurred_at": a.occurred_at,
            "location_text": a.location_text,
            "lat": a.lat,
            "lng": a.lng,
            "description": a.description,
            "injuries": a.injuries,
            "source": "driver" if a.reported_by_device else "office",
            "stage": stage(a),
            "status": a.status,
            "has_police_report": a.police_report_sha256 is not None,
            "center": centers.get(a.center_id),
            "estimate_status": a.estimate_status,
            "estimate_total": a.estimate_total,
            "liability": a.liability,
            "liability_percent": a.liability_percent,
            "deduction_total": d["total"] if (d := deductions.get(a.id)) and d["status"] == "approved" else None,
            "created_at": a.created_at,
            "version": a.version,
        }
        for a in rows
    ]


def _detail(db: Session, a: Accident) -> dict:
    events = list(db.scalars(select(AccidentEvent).where(AccidentEvent.accident_id == a.id).order_by(AccidentEvent.id)))
    users = identity.user_names(db, {e.by_user for e in events} | {a.estimate_decided_by, a.outcome_by} - {None})
    repair = maintenance.repair_summary(db, a.repair_request_id)
    actual = repair["actual_cost"] if repair else None
    return _out(db, [a])[0] | {
        "injuries_note": a.injuries_note,
        "other_party": a.other_party,
        "police_report_sha256": a.police_report_sha256,
        "police_report_no": a.police_report_no,
        "police_report_at": a.police_report_at,
        "referred_at": a.referred_at,
        "estimate_items": _items(a.estimate_items),
        "estimate_notes": a.estimate_notes,
        "estimate_file_sha256": a.estimate_file_sha256,
        "estimated_at": a.estimated_at,
        "estimate_decided_at": a.estimate_decided_at,
        "estimate_decided_by": users.get(a.estimate_decided_by),
        "estimate_reason": a.estimate_reason,
        "outcome_note": a.outcome_note,
        "outcome_at": a.outcome_at,
        "outcome_by": users.get(a.outcome_by),
        "deduction": payroll.deduction(db, a.deduction_id),
        "repair": repair,
        "cost_difference": (actual - a.estimate_total) if actual is not None and a.estimate_total else None,
        "cancel_reason": a.cancel_reason,
        "closed_at": a.closed_at,
        "photos": list(
            db.scalars(
                select(AccidentPhoto.file_sha256)
                .where(AccidentPhoto.accident_id == a.id)
                .order_by(AccidentPhoto.file_sha256)  # stable from one view to the next
            )
        ),
        "events": [
            {
                "kind": e.kind,
                "at": e.at,
                "by": users.get(e.by_user) if e.by_user else ("driver" if e.by_device else None),
                "note": e.note,
            }
            for e in events
        ],
    }


def _portal_out(db: Session, a: Accident) -> dict:
    return {
        "id": str(a.public_id),
        "number": a.number,
        "vehicle": fleet.vehicle_cards(db, [a.vehicle_id]).get(a.vehicle_id, {}),
        "occurred_at": a.occurred_at,
        "description": a.description,
        "estimate_status": a.estimate_status,
        "estimate_total": a.estimate_total,
        "estimate_items": _items(a.estimate_items),
        "estimate_notes": a.estimate_notes,
        "estimate_reason": a.estimate_reason if a.estimate_status == "rejected" else None,
        "estimated_at": a.estimated_at,
        "referred_at": a.referred_at,
        "is_new": a.seen_at is None and a.estimate_status == "none",
        "photos": list(
            db.scalars(
                select(AccidentPhoto.file_sha256)
                .where(AccidentPhoto.accident_id == a.id)
                .order_by(AccidentPhoto.file_sha256)  # stable from one view to the next
            )
        ),
    }


def _driver_out(db: Session, rows: list[Accident]) -> list[dict]:
    plates = fleet.plate_numbers(db, {a.vehicle_id for a in rows})
    return [
        {
            "id": str(a.public_id),
            "number": a.number,
            "vehicle_plate": plates.get(a.vehicle_id, ""),
            "occurred_at": a.occurred_at,
            "description": a.description,
            "stage": stage(a),
            "has_police_report": a.police_report_sha256 is not None,
            "liability": a.liability,
            "liability_percent": a.liability_percent,
            "deduction": d if (d := payroll.deduction(db, a.deduction_id)) and d["status"] == "approved" else None,
            "created_at": a.created_at,
        }
        for a in rows
    ]


# ------------------------------------------------------------------ reporting


def _flush(db: Session) -> None:
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        code = ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None


def _reported(db: Session, a: Accident, data: dict, *, by_user=None, by_device=None) -> None:
    db.add(AccidentEvent(accident_id=a.id, kind="reported", by_user=by_user, by_device=by_device))
    _add_photos(db, a, data.get("photos") or [])
    if data.get("police_report"):
        a.police_report_sha256, a.police_report_no = data["police_report"], data.get("police_report_no")
        a.police_report_at = utcnow()
        db.add(
            AccidentEvent(
                accident_id=a.id, kind="police_report", by_user=by_user, by_device=by_device, note=a.police_report_no
            )
        )
    marked = fleet.mark_accident(db, a.vehicle_id)
    driver = people.names(db, [a.driver_id]).get(a.driver_id) if a.driver_id else None
    notifications.raise_alert(
        db,
        "accident_injuries" if a.injuries else "accident_reported",
        company_id=a.company_id,
        entity_type="accident",
        entity_id=a.public_id,
        params=_alert_params(db, a) | {"driver": driver["name"] if driver else "—"},
        dedupe_key=f"acc_reported:{a.id}",
    )
    _audit(
        db,
        "accident.reported",
        a,
        actor_user_id=by_user,
        actor_type="device" if by_device else None,
        after={"injuries": a.injuries, "vehicle_marked": marked, "police_report": a.police_report_sha256 is not None},
    )
    _emit(
        db,
        "accident.reported",
        a,
        vehicle_id=str(fleet.vehicles(db, [a.vehicle_id])[a.vehicle_id].public_id),
        occurred_at=a.occurred_at.isoformat(),
        injuries=a.injuries,
        source="driver" if by_device else "office",
    )


def _fields(data: dict) -> dict:
    return {
        "lat": data.get("lat"),
        "lng": data.get("lng"),
        "location_text": data.get("location_text"),
        "description": data["description"],
        "injuries": data.get("injuries", False),
        "injuries_note": data.get("injuries_note"),
        "other_party": data.get("other_party"),
    }


def create(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    """Reported by the office. The driver is whoever held the vehicle at that time (none if nobody did)."""
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope)
    at = data.get("occurred_at") or utcnow()
    _check_time(at, OFFICE_BACKDATE)
    _check_images(db, data.get("photos") or [])
    if data.get("police_report"):
        _check_document(db, data["police_report"])
    custody = fleet.custody_ref_at(db, vehicle.id, at)
    a = Accident(
        vehicle_id=vehicle.id,
        company_id=vehicle.company_id,
        driver_id=custody.driver_id if custody else None,
        custody_id=custody.id if custody else None,
        occurred_at=at,
        reported_by_user=actor_user_id,
        **_fields(data),
    )
    db.add(a)
    _flush(db)
    db.refresh(a)
    _reported(db, a, data, by_user=actor_user_id)
    db.commit()
    return _detail(db, a)


def driver_report(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    """From the app: the vehicle the driver held at the accident time, photos from this phone's camera only, as
    many as the settings require (several angles, BRD FR-ACC-02)."""
    if db.scalar(select(Accident.id).where(Accident.client_ref == data["client_ref"])):
        raise AppError(409, "accident_exists")  # a retry: already recorded
    at = data.get("occurred_at") or utcnow()
    _check_time(at, DRIVER_DELAY)
    custody = next(iter(fleet.custodies_for_driver(db, employee_id, at, at)), None)
    if custody is None:
        raise AppError(409, "no_vehicle_in_custody")
    photos = list(dict.fromkeys(data.get("photos") or []))
    need = org.get_section(db, "accidents").min_photos
    if len(photos) < need:
        raise AppError(422, "accident_photos_required", min=need)
    _check_images(db, photos, device_id=device_id)
    if data.get("police_report"):
        _check_images(db, [data["police_report"]], device_id=device_id)
    a = Accident(
        vehicle_id=custody.vehicle_id,
        company_id=custody.company_id,
        driver_id=employee_id,
        custody_id=custody.id,
        occurred_at=at,
        client_ref=data["client_ref"],
        reported_by_device=device_id,
        **_fields(data),
    )
    db.add(a)
    _flush(db)
    db.refresh(a)
    _reported(db, a, data | {"photos": photos}, by_device=device_id)
    db.commit()
    return _driver_out(db, [a])[0]


def for_driver(db: Session, employee_id: int, *, limit: int = 20) -> list[dict]:
    """The driver's accidents (reported from the app or by the office), with the outcome and any deduction."""
    rows = db.scalars(
        select(Accident)
        .where(Accident.driver_id == employee_id, Accident.status != "cancelled")
        .order_by(Accident.occurred_at.desc(), Accident.id.desc())
        .limit(limit)
    )
    return _driver_out(db, list(rows))


def driver_police_report(db: Session, public_id, *, employee_id: int, device_id: int, data: dict) -> dict:
    """The driver photographs the police report once it is issued. A retry with the same photo is a no-op."""
    a = db.scalar(
        select(Accident).where(Accident.public_id == public_id, Accident.driver_id == employee_id).with_for_update()
    )
    if a is None:
        raise AppError(404, "accident_not_found")
    if a.police_report_sha256 is not None:
        if a.police_report_sha256 == data["file_sha256"]:
            return _driver_out(db, [a])[0]
        raise AppError(409, "police_report_exists")
    _open(a)
    _check_images(db, [data["file_sha256"]], device_id=device_id)
    a.police_report_sha256, a.police_report_no, a.police_report_at = data["file_sha256"], data.get("number"), utcnow()
    _event(db, a, "police_report", by_device=device_id, note=data.get("number"))
    notifications.resolve(db, f"acc_police:{a.id}")
    _audit(db, "accident.police_report", a, actor_type="device", after={"number": data.get("number")})
    db.commit()
    return _driver_out(db, [a])[0]


# ------------------------------------------------------------------ the office


def list_accidents(
    db: Session,
    *,
    stage_filter: str | None = None,
    status: str | None = None,
    no_police_report: bool = False,
    vehicle_public_id=None,
    driver_public_id=None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Accident), **scope)
    if status:
        q = q.where(Accident.status.in_(status.split(",")))
    if no_police_report:
        q = q.where(Accident.police_report_sha256.is_(None), Accident.status == "open")
    if vehicle_public_id:
        q = q.where(Accident.vehicle_id == fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id)
    if driver_public_id:
        q = q.where(Accident.driver_id == people.ref_by_public_id(db, driver_public_id, **scope).id)
    rows = list(db.scalars(q.order_by(Accident.occurred_at.desc(), Accident.id.desc())))
    if stage_filter:
        wanted = set(stage_filter.split(","))
        rows = [a for a in rows if stage(a) in wanted]
    return _out(db, rows[offset : offset + min(limit, 500)])


def get(db: Session, public_id, **scope) -> dict:
    return _detail(db, _get(db, public_id, **scope))


def add_photos(db: Session, public_id, *, photos: list[str], actor_user_id: int, **scope) -> dict:
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    _check_images(db, photos)
    _add_photos(db, a, photos)
    _event(db, a, "photos", by_user=actor_user_id, note=str(len(set(photos))))
    db.commit()
    return _detail(db, a)


def police_report(db: Session, public_id, *, data: dict, actor_user_id: int, **scope) -> dict:
    """Attached (or replaced) by the office until the outcome is recorded: then it is the evidence of the decision."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.liability is not None:
        raise AppError(409, "outcome_recorded")
    _check_document(db, data["file_sha256"])
    replaced = a.police_report_sha256 is not None
    a.police_report_sha256, a.police_report_no, a.police_report_at = data["file_sha256"], data.get("number"), utcnow()
    _event(
        db, a, "police_report", by_user=actor_user_id, note=data.get("number") or (":replaced" if replaced else None)
    )
    notifications.resolve(db, f"acc_police:{a.id}")
    _audit(db, "accident.police_report", a, actor_user_id=actor_user_id, after={"replaced": replaced})
    db.commit()
    return _detail(db, a)


def refer(db: Session, public_id, *, center_public_id, note: str | None, actor_user_id: int, **scope) -> dict:
    """The maintenance manager picks the center that estimates the damage (BRD FR-ACC-04); it sees the accident in
    its portal. Another center can be chosen until an estimate is pending or approved."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.estimate_status == "pending":
        raise AppError(409, "estimate_pending")
    if a.estimate_status == "approved":
        raise AppError(409, "estimate_approved")
    center = maintenance.center_brief(db, center_public_id)
    if a.center_id == center["id"] and a.estimate_status == "none":
        return _detail(db, a)
    a.center_id, a.referred_by, a.referred_at, a.seen_at = center["id"], actor_user_id, utcnow(), None
    a.estimate_status = "none"  # a rejected estimate stays in the timeline; the center estimates again
    a.estimate_total, a.estimate_items, a.estimate_notes, a.estimate_file_sha256 = None, [], None, None
    a.estimated_by = a.estimated_at = a.estimate_decided_by = a.estimate_decided_at = a.estimate_reason = None
    _event(db, a, "referred", by_user=actor_user_id, note=center["name"] + (f" — {note}" if note else ""))
    notifications.resolve(db, f"acc_reported:{a.id}")
    _audit(db, "accident.referred", a, actor_user_id=actor_user_id, after={"center": center["name"]})
    _emit(db, "accident.referred", a, center_id=center["public_id"])
    db.commit()
    return _detail(db, a)


def decide_estimate(db: Session, public_id, *, approve: bool, reason: str | None, actor_user_id: int, **scope) -> dict:
    """The maintenance manager approves the estimate before it is used for a deduction (BRD FR-ACC-05)."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.estimate_status != "pending":
        raise AppError(409, "estimate_not_pending")
    if not approve and not reason:
        raise AppError(422, "reason_required")
    a.estimate_status = "approved" if approve else "rejected"
    a.estimate_decided_by, a.estimate_decided_at, a.estimate_reason = actor_user_id, utcnow(), reason
    _event(db, a, "estimate_approved" if approve else "estimate_rejected", by_user=actor_user_id, note=reason)
    notifications.resolve(db, f"acc_estimate:{a.id}")
    _audit(
        db,
        "accident.estimate_approved" if approve else "accident.estimate_rejected",
        a,
        actor_user_id=actor_user_id,
        after={"total": a.estimate_total, "reason": reason},
    )
    if approve:
        _emit(db, "accident.estimate.approved", a, total=str(a.estimate_total))
    db.commit()
    return _detail(db, a)


def record_outcome(db: Session, public_id, *, data: dict, actor_user_id: int, **scope) -> dict:
    """The liability per the attached police report (UAT-24: refused without it) and, when the driver is liable,
    the deduction: the approved estimate in full or by the liability percentage, in monthly installments (UAT-26)."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.liability is not None:
        raise AppError(409, "outcome_recorded")
    if a.police_report_sha256 is None:
        raise AppError(409, "police_report_required")
    liability, percent = data["liability"], data.get("percent")
    amount = None
    if liability != "none":
        if a.driver_id is None:
            raise AppError(409, "accident_has_no_driver")
        if a.estimate_status != "approved":
            raise AppError(409, "estimate_not_approved")
        if liability == "shared" and percent is None:
            raise AppError(422, "liability_percent_required")
        if liability == "shared" and percent >= 100:
            raise AppError(422, "shared_percent_below_100")
        if data.get("installments") is None:
            raise AppError(422, "installments_required")
        percent = Decimal(percent if percent is not None else 100).quantize(Decimal("0.01"))
        amount = (a.estimate_total * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        start = data.get("start_month") or payroll.add_months(today(), 1)
        a.deduction_id = payroll.create_deduction(
            db,
            employee_id=a.driver_id,
            company_id=a.company_id,
            source_type="accident",
            source_id=a.id,
            reason=data.get("reason") or f"#{a.number}",
            total=amount,
            installments=data["installments"],
            start_month=start,
            actor_user_id=actor_user_id,
        )
    a.liability, a.liability_percent = liability, (percent if liability != "none" else None)
    a.outcome_note, a.outcome_by, a.outcome_at = data.get("note"), actor_user_id, utcnow()
    _event(db, a, "outcome", by_user=actor_user_id, note=data.get("note"))
    _audit(
        db,
        "accident.outcome",
        a,
        actor_user_id=actor_user_id,
        after={"liability": liability, "percent": a.liability_percent, "deduction": amount},
    )
    _emit(
        db,
        "accident.outcome.recorded",
        a,
        liability=liability,
        percent=None if a.liability_percent is None else str(a.liability_percent),
        deduction=None if amount is None else str(amount),
    )
    db.commit()
    return _detail(db, a)


def create_repair(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    """Sends the vehicle for repair to the center that estimated the damage: a maintenance request whose approved
    quote is the estimate. Its approved invoices are the actual cost (BRD FR-ACC-08)."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.estimate_status != "approved":
        raise AppError(409, "estimate_not_approved")
    if a.repair_request_id is not None:
        raise AppError(409, "repair_exists")
    a.repair_request_id = maintenance.accident_repair(
        db,
        vehicle_id=a.vehicle_id,
        company_id=a.company_id,
        driver_id=a.driver_id,
        center_id=a.center_id,
        description=f"#{a.number}: {a.description}"[:2000],
        amount=a.estimate_total,
        items=a.estimate_items,
        estimate_by=a.estimated_by,
        approved_by=actor_user_id,
    )
    _event(db, a, "repair_requested", by_user=actor_user_id)
    _audit(db, "accident.repair_requested", a, actor_user_id=actor_user_id)
    db.commit()
    return _detail(db, a)


def close(db: Session, public_id, *, note: str | None, actor_user_id: int, **scope) -> dict:
    """Closed once the outcome is recorded. A vehicle still "in an accident" (not at a center) is released."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.liability is None:
        raise AppError(409, "outcome_required")
    a.status, a.closed_at = "closed", utcnow()
    fleet.clear_accident(db, a.vehicle_id)
    _resolve_all(db, a)
    _event(db, a, "closed", by_user=actor_user_id, note=note)
    _audit(db, "accident.closed", a, actor_user_id=actor_user_id)
    db.commit()
    return _detail(db, a)


def cancel(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """Reported in error. Not once a deduction or a repair came out of it."""
    a = _get(db, public_id, lock=True, **scope)
    _open(a)
    if a.liability is not None:
        raise AppError(409, "outcome_recorded")
    if a.repair_request_id is not None:
        raise AppError(409, "repair_exists")
    a.status, a.cancel_reason = "cancelled", reason
    fleet.clear_accident(db, a.vehicle_id)
    _resolve_all(db, a)
    _event(db, a, "cancelled", by_user=actor_user_id, note=reason)
    _audit(db, "accident.cancelled", a, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _detail(db, a)


def _file(db: Session, a: Accident, sha256: str, *, police_report: bool = True) -> files.FileInfo:
    owned = (
        db.get(AccidentPhoto, (a.id, sha256)) is not None
        or sha256 == a.estimate_file_sha256
        or (police_report and sha256 == a.police_report_sha256)
    )
    if not owned:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def accident_file(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    return _file(db, _get(db, public_id, **scope), sha256)


# ------------------------------------------------------------------ the center's portal


def _for_center(db: Session, public_id, center_id: int, *, lock=False) -> Accident:
    q = select(Accident).where(Accident.public_id == public_id, Accident.center_id == center_id)
    a = db.scalar(q.with_for_update() if lock else q)
    if a is None:  # referred elsewhere, or never: the portal does not even confirm it exists
        raise AppError(404, "accident_not_found")
    return a


def portal_list(db: Session, *, user_id: int, active: bool = True, limit: int = 100) -> list[dict]:
    center_id = maintenance.portal_center_id(db, user_id)
    q = select(Accident).where(Accident.center_id == center_id)
    waiting = Accident.estimate_status.in_(("none", "rejected", "pending")) & (Accident.status == "open")
    q = q.where(waiting) if active else q.where(~waiting)
    rows = db.scalars(q.order_by(Accident.referred_at.desc(), Accident.id.desc()).limit(min(limit, 300)))
    return [_portal_out(db, a) for a in rows]


def portal_get(db: Session, public_id, *, user_id: int) -> dict:
    a = _for_center(db, public_id, maintenance.portal_center_id(db, user_id))
    if a.seen_at is None:
        a.seen_at = utcnow()
        db.commit()
    return _portal_out(db, a)


def submit_estimate(db: Session, public_id, *, user_id: int, data: dict) -> dict:
    """The center's damage estimate, item by item (BRD FR-ACC-04): it waits for the maintenance manager."""
    a = _for_center(db, public_id, maintenance.portal_center_id(db, user_id), lock=True)
    _open(a)
    if a.estimate_status not in ("none", "rejected"):
        raise AppError(409, "estimate_not_expected", status=a.estimate_status)
    items = [dict(i) for i in data["items"]]
    total = Decimal(data["total"]).quantize(CENT)
    if _items_total(items) != total:
        raise AppError(422, "estimate_items_mismatch", total=str(total), items=str(_items_total(items)))
    if data.get("file_sha256"):
        _check_document(db, data["file_sha256"], user_id=user_id)
    _check_images(db, data.get("photos") or [], user_id=user_id)
    a.estimate_status, a.estimate_total, a.estimate_notes = "pending", total, data.get("notes")
    a.estimate_items = [{k: str(v) if isinstance(v, Decimal) else v for k, v in i.items()} for i in items]
    a.estimate_file_sha256, a.estimated_by, a.estimated_at = data.get("file_sha256"), user_id, utcnow()
    a.estimate_decided_by = a.estimate_decided_at = a.estimate_reason = None
    a.seen_at = a.seen_at or utcnow()
    _add_photos(db, a, data.get("photos") or [])
    _event(db, a, "estimate_submitted", by_user=user_id, note=str(total))
    center = maintenance.centers_brief(db, [a.center_id])[a.center_id]
    notifications.raise_alert(
        db,
        "accident_estimate_submitted",
        company_id=a.company_id,
        entity_type="accident",
        entity_id=a.public_id,
        params=_alert_params(db, a) | {"center": center["name"], "amount": str(total)},
        dedupe_key=f"acc_estimate:{a.id}",
    )
    _audit(db, "accident.estimate_submitted", a, actor_user_id=user_id, after={"total": total})
    db.commit()
    return _portal_out(db, a)


def portal_file(db: Session, public_id, sha256: str, *, user_id: int) -> files.FileInfo:
    a = _for_center(db, public_id, maintenance.portal_center_id(db, user_id))
    return _file(db, a, sha256, police_report=False)


# ------------------------------------------------------------------ alerts and the dashboard


def scan_police_reports(db: Session) -> int:
    """Open accidents still without a police report after the days set in the settings (daily)."""
    days = org.get_section(db, "accidents").police_report_alert_days
    rows = list(
        db.scalars(
            select(Accident).where(
                Accident.status == "open",
                Accident.police_report_sha256.is_(None),
                Accident.created_at < utcnow() - timedelta(days=days),
            )
        )
    )
    raised = 0
    for a in rows:
        waited = (utcnow() - a.created_at).days
        raised += notifications.raise_alert(
            db,
            "accident_awaiting_police_report",
            company_id=a.company_id,
            entity_type="accident",
            entity_id=a.public_id,
            params=_alert_params(db, a) | {"days": waited},
            dedupe_key=f"acc_police:{a.id}",
        )
    db.commit()
    return raised


def _month_start() -> datetime:
    return datetime.combine(today().replace(day=1), time.min, tzinfo=KUWAIT)


def counts(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> dict:
    """Dashboard: open accidents, those still without a police report, estimates and outcomes waiting."""
    rows = list(db.scalars(_scoped(select(Accident).where(Accident.status == "open"), all_companies, company_ids)))
    stages = [stage(a) for a in rows]
    return {
        "open": len(rows),
        "no_police_report": sum(1 for a in rows if a.police_report_sha256 is None),
        "estimate_pending": stages.count("estimate_pending"),
        "awaiting_outcome": stages.count("awaiting_outcome"),
        "this_month": db.scalar(
            _scoped(
                select(func.count())
                .select_from(Accident)
                .where(Accident.status != "cancelled", Accident.occurred_at >= _month_start()),
                all_companies,
                company_ids,
            )
        ),
    }
