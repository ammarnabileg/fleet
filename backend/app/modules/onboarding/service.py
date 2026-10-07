"""Driver self-registration.

After the activation link, the driver enters his civil ID and nationality, photographs his documents (with their
expiry dates), and declares the vehicle he holds with its odometer and condition photos. Nothing reaches the
official records until a reviewer approves; approval applies everything in one transaction (employee data,
documents, custody from the moment the driver sent it) or nothing, with the precise reason (an expired licence,
a vehicle held by someone else, photos older than the 7-day handover limit...). A rejection goes back to the driver
with its reason, over WhatsApp too.
"""

import logging
from collections.abc import Iterable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import messaging
from app.core.clock import utcnow
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.documents import service as documents
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.i18n import service as i18n
from app.modules.integrations import service as integrations
from app.modules.notifications import service as notifications
from app.modules.onboarding.models import Submission
from app.modules.org import service as org
from app.modules.payroll import service as payroll
from app.modules.people import service as people

log = logging.getLogger("fleet.onboarding")
OPEN = ("draft", "rejected")  # the driver may still edit


def _get(db: Session, employee_id: int, *, lock: bool = False) -> Submission | None:
    q = select(Submission).where(Submission.employee_id == employee_id)
    return db.scalar(q.with_for_update() if lock else q)


def needed(db: Session, employee_id: int) -> bool:
    """True until the driver has an approved registration."""
    submission = _get(db, employee_id)
    return submission is None or submission.status != "approved"


def start(db: Session, driver: people.EmployeeRef) -> None:
    """Opens a registration (in the caller's transaction) unless one is already open or approved."""
    if _get(db, driver.id) is None:
        db.add(Submission(employee_id=driver.id, company_id=driver.company_id, status="draft", data={}))
        db.flush()


# ------------------------------------------------------------------ driver side


def for_driver(db: Session, employee_id: int) -> dict:
    submission = _get(db, employee_id)
    settings = org.get_section(db, "onboarding")
    types = {t["code"]: t for t in documents.list_types(db) if t["applies_to"] == "employee"}
    schemes = payroll.offered_schemes(db, people.ref(db, employee_id).platform_id)
    return {
        "known": people.registration_known(db, employee_id),
        "nationalities": people.nationalities(),
        "schemes": schemes,
        "scheme_required": bool(schemes),
        "required": submission is not None and submission.status in OPEN,
        "status": submission.status if submission else "none",
        "data": submission.data if submission else {},
        "review_note": submission.review_note if submission else None,
        "required_documents": [c for c in settings.required_documents if c in types],
        "require_bank": settings.require_bank,
        "vehicle_photos": list(settings.vehicle_photos),
        "document_types": [
            {"code": t["code"], "name": t["name"], "requires_expiry": t["requires_expiry"]} for t in types.values()
        ],
    }


def _file_refs(data: dict) -> list[tuple[str, bool]]:
    """(sha256, must come from the camera) for every file the registration points to."""
    refs = []
    for doc in data.get("documents") or ():
        refs += [(doc[k], False) for k in ("front_sha256", "back_sha256") if doc.get(k)]
    vehicle = data.get("vehicle") or {}
    if vehicle.get("odometer_photo"):
        refs.append((vehicle["odometer_photo"], True))
    refs += [(p["sha256"], True) for p in vehicle.get("photos") or ()]
    return refs


def _check_files(db: Session, data: dict, device_id: int) -> None:
    """Only files this phone uploaded; vehicle and odometer photos from the app's camera."""
    for sha, camera in _file_refs(data):
        info = files.get(db, sha)
        if info.uploaded_by_device != device_id:
            raise AppError(422, "file_not_yours")
        if camera and (info.source != "camera" or info.content_type not in files.IMAGES):
            raise AppError(422, "photo_not_from_camera")


def _without_locked(db: Session, employee_id: int, data: dict) -> dict:
    """The office's values win: what is already on his record is not his to change (approval fills empty fields only,
    and the reviewer should not see a value that will not apply)."""
    locked = people.registration_known(db, employee_id)["locked"]
    return {k: v for k, v in data.items() if k not in locked}


def save_draft(db: Session, employee_id: int, device_id: int, data: dict) -> dict:
    submission = _get(db, employee_id, lock=True)
    if submission is None or submission.status not in OPEN:
        raise AppError(409, "onboarding_not_open")
    data = _without_locked(db, employee_id, data)
    if data.get("nationality") and not people.is_nationality(data["nationality"]):
        raise AppError(422, "nationality_unknown")  # chosen from the list, never typed
    _check_files(db, data, device_id)
    submission.data, submission.status = data, "draft"
    submission.version += 1
    submission.updated_at = func.now()
    db.commit()
    return for_driver(db, employee_id)


def _missing(db: Session, data: dict, driver: people.EmployeeRef) -> list[str]:
    settings = org.get_section(db, "onboarding")
    locked = people.registration_known(db, driver.id)["locked"]
    types = documents.employee_type_codes(db)
    docs = {d["type_code"]: d for d in data.get("documents") or ()}
    for code in docs:
        if code not in types:
            raise AppError(422, "document_type_mismatch")
    missing = []
    for code, doc in docs.items():
        if not doc.get("front_sha256") or (types[code] and not doc.get("expiry_date")):
            missing.append(f"document.{code}")
    missing += [f"document.{code}" for code in settings.required_documents if code in types and code not in docs]
    if settings.require_bank:
        missing += [f for f in ("iban", "bank_name") if not data.get(f) and f not in locked]
    offered = {s["id"] for s in payroll.offered_schemes(db, driver.platform_id)}
    if offered and data.get("scheme_id") not in offered:
        missing.append("scheme")  # his platform's schemes: he chooses one (the office decides at the review)
    if not data.get("no_vehicle"):
        vehicle = data.get("vehicle") or {}
        missing += [f"vehicle.{f}" for f in ("plate_number", "odometer_km", "odometer_photo") if vehicle.get(f) is None]
        positions = {p["position"] for p in vehicle.get("photos") or ()}
        missing += [f"vehicle.photo.{p}" for p in settings.vehicle_photos if p not in positions]
    return sorted(set(missing))


def submit(db: Session, employee_id: int, device_id: int) -> dict:
    submission = _get(db, employee_id, lock=True)
    if submission is None or submission.status not in OPEN:
        raise AppError(409, "onboarding_not_open")
    data = submission.data = _without_locked(db, employee_id, submission.data)  # the office may have filled some since
    missing = _missing(db, data, people.ref(db, employee_id))
    if missing:
        raise AppError(422, "onboarding_incomplete", missing=", ".join(missing))
    _check_files(db, data, device_id)
    vehicle = None if data.get("no_vehicle") else data.get("vehicle")
    if vehicle:  # tell the driver now, not days later at review
        found = fleet.vehicle_by_plate(db, vehicle["plate_number"])
        if found is None:
            raise AppError(422, "plate_not_found", plate=vehicle["plate_number"])
        holder = fleet.holder(db, found.id)
        if holder is not None and holder != employee_id:
            raise AppError(409, "vehicle_has_custody")
    submission.status, submission.submitted_at = "submitted", utcnow()
    submission.review_note = None
    submission.version += 1
    driver = people.ref(db, employee_id)
    notifications.raise_alert(
        db,
        "onboarding_submitted",
        company_id=submission.company_id,
        entity_type="onboarding",
        entity_id=submission.public_id,
        params={"driver": driver.name},
        dedupe_key=f"onboarding:{submission.id}",
    )
    audit.record(
        db,
        action="onboarding.submitted",
        entity_type="onboarding",
        entity_id=submission.public_id,
        actor_type="device",
        company_id=submission.company_id,
    )
    db.commit()
    return for_driver(db, employee_id)


# ------------------------------------------------------------------ review


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Submission.company_id.in_(list(company_ids)))


def _row(db: Session, public_id, *, lock: bool = False, all_companies: bool, company_ids) -> Submission:
    q = _scoped(select(Submission).where(Submission.public_id == public_id), all_companies, company_ids)
    submission = db.scalar(q.with_for_update() if lock else q)
    if submission is None:
        raise AppError(404, "onboarding_not_found")
    return submission


def _out(s: Submission, names: dict) -> dict:
    vehicle = None if s.data.get("no_vehicle") else s.data.get("vehicle") or {}
    return {
        "id": str(s.public_id),
        "employee": names.get(s.employee_id),
        "company_id": s.company_id,
        "status": s.status,
        "plate_number": vehicle.get("plate_number") if vehicle else None,
        "submitted_at": s.submitted_at,
        "reviewed_at": s.reviewed_at,
        "review_note": s.review_note,
    }


def list_submissions(
    db: Session,
    *,
    status: str | None,
    all_companies: bool,
    company_ids: Iterable[int],
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    q = _scoped(select(Submission), all_companies, company_ids)
    if status:
        q = q.where(Submission.status == status)
    q = q.order_by(Submission.submitted_at.desc().nulls_last(), Submission.id.desc()).limit(min(limit, 200))
    rows = list(db.scalars(q.offset(offset)))
    names = people.names(db, [s.employee_id for s in rows])
    return [_out(s, names) for s in rows]


def detail(db: Session, public_id, **scope) -> dict:
    s = _row(db, public_id, **scope)
    driver = people.ref(db, s.employee_id)
    # the reviewer sees what the record will hold: the office's values where the driver had nothing to fill
    known = people.registration_known(db, s.employee_id)
    data = s.data | {f: known[f] for f in ("civil_id", "nationality", "bank_name") if f in known["locked"]}
    out = _out(s, people.names(db, [s.employee_id])) | {"phone": driver.phone, "data": data, "vehicle": None}
    vehicle = None if s.data.get("no_vehicle") else s.data.get("vehicle")
    if vehicle and vehicle.get("plate_number"):
        found = fleet.vehicle_by_plate(db, vehicle["plate_number"])
        holder = fleet.holder(db, found.id) if found else None
        out["vehicle"] = {
            "found": found is not None,
            "id": str(found.public_id) if found else None,
            "status": found.status if found else None,
            "held_by_other": holder is not None and holder != s.employee_id,
        }
    return out


def file(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    s = _row(db, public_id, **scope)
    if sha256 not in {sha for sha, _ in _file_refs(s.data)}:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def _notify(db: Session, driver: people.EmployeeRef, key: str, **params) -> None:
    """Best effort: the decision stands even if WhatsApp is down or he has no number on file (the app shows it too)."""
    if not driver.phone:
        return
    try:
        integrations.messenger(db).send(driver.phone, i18n.for_drivers(db, key, name=driver.name, **params))
    except messaging.DeliveryError as exc:
        log.warning("registration decision not delivered: %s", exc)


def approve(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    s = _row(db, public_id, lock=True, **scope)
    if s.status != "submitted":
        raise AppError(409, "onboarding_not_submitted")
    driver = people.ref(db, s.employee_id)
    if driver is None or driver.is_terminal:
        raise AppError(422, "employment_ended")
    data, custody = s.data, None
    try:
        people.apply_self_registration(db, driver.id, data, actor_user_id=actor_user_id)
        if data.get("scheme_id"):
            payroll.scheme_from_registration(db, driver, data["scheme_id"], actor_user_id=actor_user_id)
        owner = documents.Owner("employee", driver.id, str(driver.public_id), driver.company_id, driver.name)
        for doc in data.get("documents") or ():
            documents.add(
                db,
                owner,
                {
                    "type_code": doc["type_code"],
                    "number": doc.get("number"),
                    "expiry_date": date.fromisoformat(doc["expiry_date"]) if doc.get("expiry_date") else None,
                    "file_sha256": doc.get("front_sha256"),
                    "file_back_sha256": doc.get("back_sha256"),
                    "notes": "self-registration",
                },
                actor_user_id=actor_user_id,
                commit=False,
            )
        vehicle = None if data.get("no_vehicle") else data.get("vehicle")
        if vehicle:
            found = fleet.vehicle_by_plate(db, vehicle["plate_number"])
            if found is None:
                raise AppError(422, "plate_not_found", plate=vehicle["plate_number"])
            if fleet.holder(db, found.id) != driver.id:  # already handed over at the office: nothing to add
                custody = fleet.handover(
                    db,
                    vehicle_public_id=found.public_id,
                    driver_public_id=driver.public_id,
                    odometer_km=vehicle["odometer_km"],
                    photo_sha256=vehicle["odometer_photo"],
                    started_at=s.submitted_at,
                    kind="normal",
                    reason=None,
                    can_emergency=False,
                    actor_user_id=actor_user_id,
                    photos=vehicle.get("photos") or [],
                    commit=False,
                    **scope,
                )
        s.status, s.reviewed_at, s.reviewed_by = "approved", utcnow(), actor_user_id
        s.version += 1
        notifications.resolve(db, f"onboarding:{s.id}")
        audit.record(
            db,
            action="onboarding.approved",
            entity_type="onboarding",
            entity_id=s.public_id,
            actor_user_id=actor_user_id,
            company_id=s.company_id,
            after={"documents": len(data.get("documents") or ()), "custody": custody["id"] if custody else None},
        )
        emit(
            db,
            "employee.onboarded",
            driver.public_id,
            {
                "employee_id": str(driver.public_id),
                "custody_id": custody["id"] if custody else None,
            },
        )
        db.commit()
    except AppError:
        db.rollback()  # all or nothing
        raise
    _notify(db, driver, "messages.onboarding_approved")
    return detail(db, public_id, **scope)


def reject(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    s = _row(db, public_id, lock=True, **scope)
    if s.status != "submitted":
        raise AppError(409, "onboarding_not_submitted")
    s.status, s.review_note = "rejected", reason
    s.reviewed_at, s.reviewed_by = utcnow(), actor_user_id
    s.version += 1
    notifications.resolve(db, f"onboarding:{s.id}")
    audit.record(
        db,
        action="onboarding.rejected",
        entity_type="onboarding",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        company_id=s.company_id,
        after={"reason": reason},
    )
    db.commit()
    _notify(db, people.ref(db, s.employee_id), "messages.onboarding_rejected", reason=reason)
    return detail(db, public_id, **scope)
