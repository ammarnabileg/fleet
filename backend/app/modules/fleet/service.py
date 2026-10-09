"""Vehicles, custody (which driver had which vehicle, and when) and odometer readings.

Custody periods never overlap per vehicle or per driver; the database enforces it (two exclusion constraints), so
"who was responsible for the vehicle at time T" always has at most one answer. Every reading is checked against
the previous one of the same vehicle; a suspicious reading is stored, flagged, raises an alert and waits for review.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, business_date, today, utcnow
from app.core.db import like_pattern, violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.documents import service as documents
from app.modules.files import service as files
from app.modules.fleet.models import (
    Custody,
    CustodyPhoto,
    OdometerReading,
    Vehicle,
    VehicleChangeRequest,
    VehicleClaim,
)
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

MANUAL_STATUSES = ("available", "maintenance", "accident", "inactive")  # "assigned" follows custody
VEHICLE_FIELDS = ("plate_number", "make", "model", "year", "color", "vin", "company_id", "branch_id", "status")
UNIQUE_ERRORS = {"vehicles_plate_number_idx": "plate_taken", "vehicles_vin_key": "vin_taken"}
OVERLAP_ERRORS = {"custodies_vehicle_overlap": "vehicle_has_custody", "custodies_driver_overlap": "driver_has_custody"}
PHOTO_POSITIONS = ("front", "back", "left", "right", "interior", "other")
CLOCK_SKEW = timedelta(minutes=5)
BACKDATE_LIMIT = timedelta(days=7)
DRIVER_READING_DELAY = timedelta(hours=48)  # the app may be offline; older readings go through the office


@dataclass(frozen=True)
class VehicleRef:
    id: int
    public_id: uuid.UUID
    plate_number: str
    company_id: int
    status: str


@dataclass(frozen=True)
class CustodyRef:
    id: int
    public_id: uuid.UUID
    vehicle_id: int
    driver_id: int
    company_id: int
    started_at: datetime
    ended_at: datetime | None
    kind: str


# photos in the order a reviewer reads them: the handover then the return, around the vehicle
CUSTODY_STAGES = {"handover": 0, "return": 1}
POSITIONS = {"front": 0, "back": 1, "left": 2, "right": 3, "interior": 4, "other": 5}


def _vref(v: Vehicle) -> VehicleRef:
    return VehicleRef(v.id, v.public_id, v.plate_number, v.company_id, v.status)


def _cref(c: Custody) -> CustodyRef:
    return CustodyRef(c.id, c.public_id, c.vehicle_id, c.driver_id, c.company_id, c.started_at, c.ended_at, c.kind)


_PLATE_DIGITS = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"  # Arabic-Indic, and the Persian ones some keyboards type
_PLATE_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
_PLATE_FROM = _PLATE_DIGITS + _PLATE_DASHES
_PLATE_TO = "0123456789" * 2 + "-" * len(_PLATE_DASHES)
_PLATE_TABLE = str.maketrans(_PLATE_FROM, _PLATE_TO)


def normalize_plate(plate: str) -> str:
    """Latin digits, a plain dash for any dash a phone types, upper case, single spaces."""
    return " ".join(plate.translate(_PLATE_TABLE).upper().split())


def _scoped(q, model, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(model.company_id.in_(list(company_ids)))


# ------------------------------------------------------------------ vehicles


def _open_custodies_by_vehicle(db: Session, vehicle_ids: Iterable[int]) -> dict[int, Custody]:
    ids = list(vehicle_ids)
    if not ids:
        return {}
    q = select(Custody).where(Custody.vehicle_id.in_(ids), Custody.ended_at.is_(None))
    return {c.vehicle_id: c for c in db.scalars(q)}


def _vehicles_out(db: Session, vehicles: list[Vehicle]) -> list[dict]:
    open_ = _open_custodies_by_vehicle(db, [v.id for v in vehicles])
    drivers = people.names(db, [c.driver_id for c in open_.values()])
    out = []
    for v in vehicles:
        c = open_.get(v.id)
        out.append(
            {
                "id": str(v.public_id),
                **{f: getattr(v, f) for f in VEHICLE_FIELDS},
                "last_odometer_km": v.last_odometer_km,
                "custody": None
                if c is None
                else {
                    "id": str(c.public_id),
                    "driver": drivers.get(c.driver_id),
                    "started_at": c.started_at,
                    "kind": c.kind,
                },
                "version": v.version,
            }
        )
    return out


def _snapshot(v: Vehicle) -> dict:
    return {
        "id": str(v.public_id),
        **{f: getattr(v, f) for f in VEHICLE_FIELDS},
        "last_odometer_km": v.last_odometer_km,
        "version": v.version,
    }


def _get_vehicle(db: Session, public_id, *, all_companies: bool, company_ids: Iterable[int], lock=False) -> Vehicle:
    q = _scoped(select(Vehicle).where(Vehicle.public_id == public_id), Vehicle, all_companies, company_ids)
    vehicle = db.scalar(q.with_for_update() if lock else q)
    if vehicle is None:
        raise AppError(404, "vehicle_not_found")
    return vehicle


def _check_company(db: Session, company_id: int, all_companies: bool, company_ids: Iterable[int]) -> None:
    if not org.company_ids_exist(db, [company_id]):
        raise AppError(422, "company_not_found")
    if not (all_companies or company_id in set(company_ids)):
        raise AppError(403, "company_out_of_scope")


def _check_branch(db: Session, branch_id: int) -> None:
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")


def _flush_vehicle(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        # no rollback here: the caller's transaction (or savepoint) decides
        code = UNIQUE_ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None


def list_vehicles(
    db: Session,
    *,
    all_companies: bool,
    company_ids: Iterable[int],
    company_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query = _scoped(select(Vehicle), Vehicle, all_companies, company_ids)
    if company_id is not None:
        query = query.where(Vehicle.company_id == company_id)
    if status:
        query = query.where(Vehicle.status == status)
    if q:
        pattern = like_pattern(q.strip())
        query = query.where(
            or_(
                Vehicle.plate_number.ilike(pattern),
                Vehicle.vin.ilike(pattern),
                Vehicle.make.ilike(pattern),
                Vehicle.model.ilike(pattern),
            )
        )
    query = query.order_by(Vehicle.plate_number).limit(min(limit, 200)).offset(offset)
    return _vehicles_out(db, list(db.scalars(query)))


def get_vehicle(db: Session, public_id, **scope) -> dict:
    return _vehicles_out(db, [_get_vehicle(db, public_id, **scope)])[0]


def create_vehicle(db: Session, data: dict, *, actor_user_id: int, commit: bool = True, **scope) -> dict:
    _check_company(db, data["company_id"], **scope)
    data = {**data, "plate_number": normalize_plate(data["plate_number"])}
    data["branch_id"] = data.get("branch_id") or org.default_branch_id(db)
    _check_branch(db, data["branch_id"])
    vehicle = Vehicle(**data)
    db.add(vehicle)
    _flush_vehicle(db)
    db.refresh(vehicle)
    audit.record(
        db,
        action="vehicle.created",
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        actor_user_id=actor_user_id,
        company_id=vehicle.company_id,
        after=_snapshot(vehicle),
    )
    emit(
        db,
        "vehicle.created",
        vehicle.public_id,
        {"vehicle_id": str(vehicle.public_id), "company_id": vehicle.company_id},
    )
    if commit:
        db.commit()
    return _vehicles_out(db, [vehicle])[0]


def update_vehicle(
    db: Session, public_id, *, version: int, changes: dict, actor_user_id: int, commit: bool = True, **scope
) -> dict:
    vehicle = _get_vehicle(db, public_id, lock=True, **scope)
    if vehicle.version != version:
        raise AppError(409, "version_conflict")
    for field in ("plate_number", "company_id", "branch_id", "status"):
        if field in changes and changes[field] is None:
            raise AppError(422, "field_required", field=field)
    in_custody = vehicle.id in _open_custodies_by_vehicle(db, [vehicle.id])
    if in_custody and (
        changes.get("status", vehicle.status) != vehicle.status
        or changes.get("company_id", vehicle.company_id) != vehicle.company_id
    ):
        raise AppError(409, "vehicle_in_custody")  # return it first
    if "company_id" in changes and changes["company_id"] != vehicle.company_id:
        _check_company(db, changes["company_id"], **scope)
    if "branch_id" in changes and changes["branch_id"] != vehicle.branch_id:
        _check_branch(db, changes["branch_id"])
    if "plate_number" in changes:
        changes["plate_number"] = normalize_plate(changes["plate_number"])
    before = _snapshot(vehicle)
    for field in VEHICLE_FIELDS:
        if field in changes:
            setattr(vehicle, field, changes[field])
    vehicle.version += 1
    vehicle.updated_at = func.now()
    _flush_vehicle(db)
    db.refresh(vehicle)
    audit.record(
        db,
        action="vehicle.updated",
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        actor_user_id=actor_user_id,
        company_id=vehicle.company_id,
        before=before,
        after=_snapshot(vehicle),
    )
    emit(
        db,
        "vehicle.updated",
        vehicle.public_id,
        {"vehicle_id": str(vehicle.public_id), "company_id": vehicle.company_id},
    )
    if commit:
        db.commit()
    return _vehicles_out(db, [vehicle])[0]


# ------------------------------------------------------------------ odometer


def _previous_reading(db: Session, vehicle_id: int, before: datetime) -> OdometerReading | None:
    return db.scalar(
        select(OdometerReading)
        .where(OdometerReading.vehicle_id == vehicle_id, OdometerReading.recorded_at <= before)
        .order_by(OdometerReading.recorded_at.desc(), OdometerReading.id.desc())
        .limit(1)
    )


def _next_reading(db: Session, vehicle_id: int, after: datetime) -> OdometerReading | None:
    return db.scalar(
        select(OdometerReading)
        .where(OdometerReading.vehicle_id == vehicle_id, OdometerReading.recorded_at > after)
        .order_by(OdometerReading.recorded_at, OdometerReading.id)
        .limit(1)
    )


def _recompute_last_km(db: Session, vehicle: Vehicle) -> None:
    latest = _previous_reading(db, vehicle.id, datetime.max.replace(tzinfo=utcnow().tzinfo))
    if latest is not None:
        vehicle.last_odometer_km = latest.effective_km


def _check_photo(db: Session, sha256: str) -> files.FileInfo:
    info = files.get(db, sha256)
    if info.content_type not in files.IMAGES:
        raise AppError(422, "photo_must_be_image")
    return info


def _add_reading(
    db: Session,
    vehicle: Vehicle,
    custody: Custody | None,
    *,
    kind: str,
    value_km: int,
    photo_sha256: str,
    recorded_at: datetime,
    lat: float | None = None,
    lng: float | None = None,
    by_user: int | None = None,
    by_device: int | None = None,
    pair: OdometerReading | None = None,
) -> OdometerReading:
    """pair: the reading taken with the same photo at the same moment (a car taken from one driver and handed to
    another at once: one reading serves the return and the handover), so the photo is not counted as reused."""
    settings = org.get_section(db, "odometer")
    previous = _previous_reading(db, vehicle.id, recorded_at)
    previous_km = previous.effective_km if previous else vehicle.last_odometer_km
    flags: list[str] = []
    if previous_km is not None and value_km < previous_km:
        flags.append("lower_than_previous")
    if previous is not None and value_km > previous_km:
        driven = value_km - previous_km
        if (
            previous.kind in ("return", "end_day")
            and kind in ("handover", "start_day")
            and driven > settings.off_duty_km_alert
        ):
            flags.append("off_duty_km")
        days = max(1, (business_date(recorded_at) - previous.business_date).days)
        if driven > settings.daily_km_alert * days:
            flags.append("daily_limit")
    # a reading sent late (offline phone) lands before readings already recorded: it must fit under them too
    following = _next_reading(db, vehicle.id, recorded_at)
    if following is not None and value_km > following.effective_km:
        flags.append("higher_than_next")
    same_photo = select(func.count()).select_from(OdometerReading).where(OdometerReading.photo_sha256 == photo_sha256)
    if pair is not None:
        same_photo = same_photo.where(OdometerReading.id != pair.id)
    if db.scalar(same_photo):
        flags.append("photo_reused")
    reading = OdometerReading(
        vehicle_id=vehicle.id,
        custody_id=custody.id if custody else None,
        driver_id=custody.driver_id if custody else None,
        kind=kind,
        value_km=value_km,
        photo_sha256=photo_sha256,
        recorded_at=recorded_at,
        business_date=business_date(recorded_at),
        lat=lat,
        lng=lng,
        flags=flags,
        review_status="pending" if flags else "ok",
        created_by_user=by_user,
        created_by_device=by_device,
    )
    db.add(reading)
    db.flush()
    db.refresh(reading)
    if flags:
        names = people.names(db, {reading.driver_id, previous.driver_id if previous else None} - {None})
        driver = names.get(reading.driver_id, {}).get("name", "") if reading.driver_id else ""
        handed = names.get(previous.driver_id, {}).get("name", "") if previous and previous.driver_id else ""
        base = {"plate": vehicle.plate_number, "driver": driver, "value": value_km, "previous": previous_km}
        alert = {
            "lower_than_previous": ("odometer_lower", base),
            "off_duty_km": (  # both drivers named: who ended or handed it, who started or took it (BRD TRK-13)
                "odometer_off_duty",
                base | {"km": value_km - (previous_km or 0), "from_driver": handed or "—", "to_driver": driver or "—"},
            ),
            "daily_limit": (
                "odometer_daily_limit",
                base | {"km": value_km - (previous_km or 0), "limit": settings.daily_km_alert},
            ),
            "photo_reused": ("odometer_photo_reused", base),
            "higher_than_next": (
                "odometer_higher_than_next",
                base | {"next": following.effective_km if following else None},
            ),
        }
        for flag in flags:
            kind_, params = alert[flag]
            notifications.raise_alert(
                db,
                kind_,
                company_id=vehicle.company_id,
                entity_type="odometer_reading",
                entity_id=reading.public_id,
                params=params,
            )
    _recompute_last_km(db, vehicle)
    return reading


def _reading_out(r: OdometerReading, plates: dict[int, str] | None = None, drivers: dict | None = None) -> dict:
    return {
        "id": str(r.public_id),
        "vehicle_plate": (plates or {}).get(r.vehicle_id),
        "driver": (drivers or {}).get(r.driver_id),
        "kind": r.kind,
        "value_km": r.value_km,
        "corrected_km": r.corrected_km,
        "effective_km": r.effective_km,
        "recorded_at": r.recorded_at,
        "business_date": r.business_date,
        "lat": r.lat,
        "lng": r.lng,
        "flags": list(r.flags),
        "review_status": r.review_status,
        "review_reason": r.review_reason,
        "reviewed_at": r.reviewed_at,
        "source": "device" if r.created_by_device else "office",
    }


def _readings_out(db: Session, readings: list[OdometerReading]) -> list[dict]:
    plates = plate_numbers(db, {r.vehicle_id for r in readings})
    drivers = people.names(db, {r.driver_id for r in readings if r.driver_id})
    return [_reading_out(r, plates, drivers) for r in readings]


def list_readings(
    db: Session,
    *,
    all_companies: bool,
    company_ids: Iterable[int],
    vehicle_public_id=None,
    review_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    q = select(OdometerReading).join(Vehicle, Vehicle.id == OdometerReading.vehicle_id)
    q = _scoped(q, Vehicle, all_companies, company_ids)
    if vehicle_public_id is not None:
        q = q.where(Vehicle.public_id == vehicle_public_id)
    if review_status:
        q = q.where(OdometerReading.review_status == review_status)
    q = q.order_by(OdometerReading.recorded_at.desc(), OdometerReading.id.desc()).limit(min(limit, 200)).offset(offset)
    return _readings_out(db, list(db.scalars(q)))


def _get_reading(db: Session, public_id, *, all_companies: bool, company_ids: Iterable[int], lock=False):
    q = select(OdometerReading, Vehicle).join(Vehicle, Vehicle.id == OdometerReading.vehicle_id)
    q = _scoped(q.where(OdometerReading.public_id == public_id), Vehicle, all_companies, company_ids)
    row = db.execute(q.with_for_update() if lock else q).first()
    if row is None:
        raise AppError(404, "reading_not_found")
    return row


def review_reading(
    db: Session, public_id, *, corrected_km: int | None, reason: str, actor_user_id: int, **scope
) -> dict:
    """Accept a flagged reading as it is, or correct it. The original value is never overwritten."""
    reading, vehicle = _get_reading(db, public_id, lock=True, **scope)
    before = _reading_out(reading)
    reading.corrected_km = corrected_km
    reading.review_status = "reviewed"
    reading.reviewed_by, reading.reviewed_at, reading.review_reason = actor_user_id, func.now(), reason
    db.flush()
    db.refresh(reading)
    _recompute_last_km(db, vehicle)
    audit.record(
        db,
        action="odometer.reviewed",
        entity_type="odometer_reading",
        entity_id=reading.public_id,
        actor_user_id=actor_user_id,
        company_id=vehicle.company_id,
        before=before,
        after=_reading_out(reading),
    )
    db.commit()
    return _readings_out(db, [reading])[0]


def reading_photo(db: Session, public_id, **scope) -> files.FileInfo:
    reading, _ = _get_reading(db, public_id, **scope)
    return files.get(db, reading.photo_sha256)


def driver_reading(
    db: Session,
    *,
    employee_id: int,
    device_id: int,
    kind: str,
    value_km: int,
    photo_sha256: str,
    recorded_at: datetime,
    lat: float | None,
    lng: float | None,
) -> dict:
    """Start-of-day (or end-of-day) reading from the driver app. The photo must come from the app's camera
    upload of this same device: the app offers no gallery, and the server refuses files from anywhere else."""
    now = utcnow()
    if not (now - DRIVER_READING_DELAY <= recorded_at <= now + CLOCK_SKEW):
        raise AppError(422, "invalid_recorded_at")
    custody = db.scalar(
        select(Custody).where(
            Custody.driver_id == employee_id,
            Custody.started_at <= recorded_at,
            or_(Custody.ended_at.is_(None), Custody.ended_at > recorded_at),
        )
    )
    if custody is None:
        raise AppError(409, "no_open_custody")
    photo = _check_photo(db, photo_sha256)
    if photo.source != "camera" or photo.uploaded_by_device != device_id:
        raise AppError(422, "photo_not_from_camera")
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == custody.vehicle_id).with_for_update())
    # The same reading sent again (the app's queue retrying, whatever came after it) is already there.
    if db.scalar(
        select(OdometerReading.id).where(
            OdometerReading.custody_id == custody.id,
            OdometerReading.kind == kind,
            OdometerReading.recorded_at == recorded_at,
        )
    ):
        raise AppError(409, "reading_exists")
    # Several work sessions a day (he starts again after ending it), one open at a time: under the vehicle's lock,
    # the custody's last start or end before this one must not be the same kind. A night shift's session stays open
    # past midnight; one left open longer than any shift (forgotten) no longer holds the next start.
    last = db.scalar(
        select(OdometerReading.kind)
        .where(
            OdometerReading.custody_id == custody.id,
            OdometerReading.kind.in_(("start_day", "end_day")),
            OdometerReading.recorded_at < recorded_at,
            OdometerReading.recorded_at > recorded_at - SESSION_HOLDS,
        )
        .order_by(OdometerReading.recorded_at.desc(), OdometerReading.id.desc())
        .limit(1)
    )
    if last == kind:
        raise AppError(409, "day_already_started" if kind == "start_day" else "day_already_ended")
    reading = _add_reading(
        db,
        vehicle,
        custody,
        kind=kind,
        value_km=value_km,
        photo_sha256=photo_sha256,
        recorded_at=recorded_at,
        lat=lat,
        lng=lng,
        by_device=device_id,
    )
    db.commit()
    return _readings_out(db, [reading])[0]


# ------------------------------------------------------------------ custody


def _add_photos(db: Session, custody: Custody, stage: str, photos: list[dict] | None) -> None:
    for photo in {p["sha256"]: p for p in photos or ()}.values():
        db.add(
            CustodyPhoto(custody_id=custody.id, stage=stage, position=photo["position"], file_sha256=photo["sha256"])
        )
    db.flush()


def _photos_out(db: Session, custody_id: int) -> list[dict]:
    q = (
        select(CustodyPhoto)
        .where(CustodyPhoto.custody_id == custody_id)
        .order_by(
            case(CUSTODY_STAGES, value=CustodyPhoto.stage),
            case(POSITIONS, value=CustodyPhoto.position),
            CustodyPhoto.file_sha256,
        )
    )
    return [{"stage": p.stage, "position": p.position, "sha256": p.file_sha256} for p in db.scalars(q)]


def custody_photo(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    custody = db.scalar(_scoped(select(Custody).where(Custody.public_id == public_id), Custody, **scope))
    if (
        custody is None
        or db.get(CustodyPhoto, (custody.id, "handover", sha256)) is None
        and db.get(CustodyPhoto, (custody.id, "return", sha256)) is None
    ):
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def _custodies_out(db: Session, custodies: list[Custody]) -> list[dict]:
    plates = plate_numbers(db, {c.vehicle_id for c in custodies})
    drivers = people.names(db, {c.driver_id for c in custodies})
    vehicle_ids = (
        {
            v_id: str(p)
            for v_id, p in db.execute(
                select(Vehicle.id, Vehicle.public_id).where(Vehicle.id.in_({c.vehicle_id for c in custodies}))
            )
        }
        if custodies
        else {}
    )
    return [
        {
            "id": str(c.public_id),
            "vehicle": {"id": vehicle_ids.get(c.vehicle_id), "plate_number": plates.get(c.vehicle_id)},
            "driver": drivers.get(c.driver_id),
            "company_id": c.company_id,
            "started_at": c.started_at,
            "ended_at": c.ended_at,
            "kind": c.kind,
            "reason": c.reason,
            "needs_review": c.needs_review,
        }
        for c in custodies
    ]


def _check_moment(t: datetime) -> None:
    now = utcnow()
    if t > now + CLOCK_SKEW:
        raise AppError(422, "time_in_future")
    if t < now - BACKDATE_LIMIT:
        raise AppError(422, "time_too_old")


def handover(
    db: Session,
    *,
    vehicle_public_id,
    driver_public_id,
    odometer_km: int,
    photo_sha256: str,
    started_at: datetime | None,
    kind: str,
    reason: str | None,
    can_emergency: bool,
    actor_user_id: int,
    photos: list[dict] | None = None,
    commit: bool = True,
    **scope,
) -> dict:
    """`photos`: condition photos [{"position", "sha256"}]. commit=False keeps everything in the caller's
    transaction (an approved self-registration applies all of its parts at once).
    An emergency handover skips the normal checks (vehicle status, driver status, expired licence), needs
    custody.emergency and a reason, and waits for review. Overlaps and ended employment are never skipped."""
    started_at = started_at or utcnow()
    _check_moment(started_at)
    vehicle = _get_vehicle(db, vehicle_public_id, lock=True, **scope)
    driver = people.ref_by_public_id(db, driver_public_id, **scope)
    if kind == "emergency":
        _check_driver(driver)
        if not can_emergency:
            raise AppError(403, "permission_denied", permission="custody.emergency")
        if not reason:
            raise AppError(422, "reason_required")
        if vehicle.status == "inactive":
            raise AppError(409, "vehicle_not_available", status=vehicle.status)
    else:
        _check_can_take(db, vehicle, driver, started_at)
    _check_photo(db, photo_sha256)
    for photo in photos or ():
        _check_photo(db, photo["sha256"])
    custody = _start_custody(
        db,
        vehicle,
        driver,
        started_at=started_at,
        kind=kind,
        reason=reason,
        odometer_km=odometer_km,
        photo_sha256=photo_sha256,
        handed_over_by=actor_user_id,
        by_user=actor_user_id,
        photos=photos,
    )
    if kind == "emergency":
        notifications.raise_alert(
            db,
            "emergency_custody",
            company_id=vehicle.company_id,
            entity_type="custody",
            entity_id=custody.public_id,
            params={"plate": vehicle.plate_number, "driver": driver.name, "reason": reason},
        )
    out = _custodies_out(db, [custody])[0]
    audit.record(
        db,
        action="custody.started",
        entity_type="custody",
        entity_id=custody.public_id,
        actor_user_id=actor_user_id,
        company_id=vehicle.company_id,
        after=out | {"odometer_km": odometer_km},
    )
    # the app reads "my car" again when told
    notifications.notify_driver(db, driver.id, "vehicle_handed_over", params={"plate": vehicle.plate_number})
    if commit:
        db.commit()
    return out


def _check_driver(driver: people.EmployeeRef) -> None:
    if not driver.is_driver:
        raise AppError(422, "not_a_driver")
    if driver.is_terminal:
        raise AppError(422, "employment_ended")


def _check_can_take(db: Session, vehicle: Vehicle, driver: people.EmployeeRef, started_at: datetime) -> None:
    """A normal handover: the vehicle free, the driver working with a licence valid that day."""
    _check_driver(driver)
    if vehicle.status not in ("available", "assigned"):  # assigned: the overlap check gives the precise error
        raise AppError(409, "vehicle_not_available", status=vehicle.status)
    if not driver.is_working:
        raise AppError(422, "driver_not_working")
    has_license, expiry = documents.current_expiry(db, "driving_license", "employee", driver.id)
    if has_license and expiry is not None and expiry < business_date(started_at):
        raise AppError(422, "driving_license_expired", date=expiry.isoformat())


def _start_custody(
    db: Session,
    vehicle: Vehicle,
    driver: people.EmployeeRef,
    *,
    started_at: datetime,
    kind: str,
    reason: str | None,
    odometer_km: int,
    photo_sha256: str,
    handed_over_by: int,
    by_user: int | None = None,
    by_device: int | None = None,
    photos: list[dict] | None = None,
    pair: OdometerReading | None = None,
) -> Custody:
    """The custody, its handover reading and photos, the vehicle assigned (vehicle locked, checks done). pair: the
    return reading taken at the same moment with the same photo, when the car passes from one driver to another."""
    custody = Custody(
        vehicle_id=vehicle.id,
        driver_id=driver.id,
        company_id=vehicle.company_id,
        started_at=started_at,
        kind=kind,
        reason=reason,
        needs_review=kind == "emergency",
        handed_over_by=handed_over_by,
    )
    try:
        with db.begin_nested():
            db.add(custody)
            db.flush()
    except IntegrityError as exc:
        code = OVERLAP_ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None
    db.refresh(custody)
    _add_reading(
        db,
        vehicle,
        custody,
        kind="handover",
        value_km=odometer_km,
        photo_sha256=photo_sha256,
        recorded_at=started_at,
        by_user=by_user,
        by_device=by_device,
        pair=pair,
    )
    _add_photos(db, custody, "handover", photos)
    _close_pending_claim(db, driver.id, vehicle, custody, decided_by=by_user)
    vehicle.status = "assigned"
    vehicle.version += 1
    emit(
        db,
        "custody.started",
        custody.public_id,
        {
            "custody_id": str(custody.public_id),
            "vehicle_id": str(vehicle.public_id),
            "driver_id": str(driver.public_id),
            "started_at": started_at.isoformat(),
            "kind": kind,
        },
    )
    return custody


def _close_pending_claim(
    db: Session, driver_id: int, vehicle: Vehicle, custody: Custody, *, decided_by: int | None
) -> None:
    """A custody started for the driver, however (the office, a transfer, his claim approved, a car collected from a
    center): the car he registered and is still waiting for is settled with it. The same car: approved, linked to the
    custody. Another car: superseded, and he is told; the office's alert closes either way."""
    claim = db.scalar(
        select(VehicleClaim)
        .where(VehicleClaim.employee_id == driver_id, VehicleClaim.status == "pending")
        .with_for_update()
    )
    if claim is None:
        return
    claim.decided_by, claim.decided_at = decided_by, utcnow()
    notifications.resolve(db, f"vehicle_claim:{claim.id}")
    if claim.vehicle_id == vehicle.id:
        claim.status, claim.custody_id = "approved", custody.id
        notifications.notify_driver(db, driver_id, "vehicle_claim_approved", params={"plate": vehicle.plate_number})
        return
    claim.status, claim.note = "superseded", CLAIM_SUPERSEDED_NOTE
    plate = db.scalar(select(Vehicle.plate_number).where(Vehicle.id == claim.vehicle_id))
    notifications.notify_driver(db, driver_id, "vehicle_claim_superseded", params={"plate": plate})


CLAIM_SUPERSEDED_NOTE = "اتسلمت عربية تانية"


def hand_back_after_maintenance(
    db: Session,
    vehicle_id: int,
    driver_id: int,
    *,
    odometer_km: int,
    photo_sha256: str,
    at: datetime,
    handed_over_by: int,
    device_id: int,
) -> dict:
    """The driver collected the vehicle from the center that repaired it: it is his again, from his own reading
    and camera photo, without an office handover. handed_over_by is the center account that released it. A
    driver who now holds another vehicle, has left, or whose licence expired is refused: the office hands over."""
    _check_moment(at)
    vehicle = _vehicle_for_update(db, vehicle_id)
    driver = people.ref(db, driver_id)
    _check_can_take(db, vehicle, driver, at)
    _check_photo(db, photo_sha256)
    custody = _start_custody(
        db,
        vehicle,
        driver,
        started_at=at,
        kind="normal",
        reason=None,
        odometer_km=odometer_km,
        photo_sha256=photo_sha256,
        handed_over_by=handed_over_by,
        by_device=device_id,
    )
    out = _custodies_out(db, [custody])[0]
    audit.record(
        db,
        action="custody.started",
        entity_type="custody",
        entity_id=custody.public_id,
        actor_type="device",
        company_id=vehicle.company_id,
        after=out | {"odometer_km": odometer_km, "after_maintenance": True},
    )
    return out


def return_vehicle(
    db: Session,
    public_id,
    *,
    odometer_km: int,
    photo_sha256: str,
    ended_at: datetime | None,
    actor_user_id: int,
    photos: list[dict] | None = None,
    **scope,
) -> dict:
    custody = db.scalar(
        _scoped(select(Custody).where(Custody.public_id == public_id), Custody, **scope).with_for_update()
    )
    if custody is None:
        raise AppError(404, "custody_not_found")
    if custody.ended_at is not None:
        raise AppError(409, "custody_closed")
    ended_at = ended_at or utcnow()
    _check_moment(ended_at)
    if ended_at <= custody.started_at:
        raise AppError(422, "ended_before_start")
    _check_photo(db, photo_sha256)
    for photo in photos or ():
        _check_photo(db, photo["sha256"])
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == custody.vehicle_id).with_for_update())
    # the app reads "my car" again when told (told first: what the return closes is the newer notice)
    notifications.notify_driver(db, custody.driver_id, "vehicle_returned", params={"plate": vehicle.plate_number})
    out, _ = _end_custody(db, custody, vehicle, ended_at, odometer_km, photo_sha256, actor_user_id, photos)
    db.commit()
    return out


def _end_custody(
    db: Session,
    custody: Custody,
    vehicle: Vehicle,
    ended_at: datetime,
    odometer_km: int,
    photo_sha256: str,
    actor_user_id: int,
    photos: list[dict] | None = None,
) -> tuple[dict, OdometerReading]:
    """The custody ended with its return reading and photos, the vehicle free: its output and the return reading."""
    custody.ended_at, custody.returned_by = ended_at, actor_user_id
    db.flush()
    reading = _add_reading(
        db,
        vehicle,
        custody,
        kind="return",
        value_km=odometer_km,
        photo_sha256=photo_sha256,
        recorded_at=ended_at,
        by_user=actor_user_id,
    )
    _add_photos(db, custody, "return", photos)
    if vehicle.status == "assigned":
        vehicle.status = "available"
    vehicle.version += 1
    notifications.resolve(db, f"driver_left:{custody.id}")
    _close_change_request(db, custody, vehicle, actor_user_id)
    out = _custodies_out(db, [custody])[0]
    audit.record(
        db,
        action="custody.ended",
        entity_type="custody",
        entity_id=custody.public_id,
        actor_user_id=actor_user_id,
        company_id=custody.company_id,
        after=out | {"odometer_km": odometer_km},
    )
    emit(
        db,
        "custody.ended",
        custody.public_id,
        {
            "custody_id": str(custody.public_id),
            "vehicle_id": str(vehicle.public_id),
            "ended_at": ended_at.isoformat(),
        },
    )
    return out, reading


# ------------------------------------------------------------------ a car taken from one driver for another


def _in_scope(company_id: int, all_companies: bool, company_ids: Iterable[int]) -> bool:
    return all_companies or company_id in set(company_ids)


def transfer_check(db: Session, *, vehicle_public_id, driver_public_id, **scope) -> dict:
    """Before handing the car X to the driver A: who holds X now, the car A holds now, and how it can be done."""
    vehicle = _get_vehicle(db, vehicle_public_id, **scope)
    driver = people.ref_by_public_id(db, driver_public_id, **scope)
    held = db.scalar(select(Custody).where(Custody.vehicle_id == vehicle.id, Custody.ended_at.is_(None)))
    his = db.scalar(
        select(Custody).where(
            Custody.driver_id == driver.id, Custody.ended_at.is_(None), Custody.vehicle_id != vehicle.id
        )
    )
    if his is not None and not _in_scope(his.company_id, **scope):
        raise AppError(403, "company_out_of_scope")  # as transfer() refuses it
    names = people.names(db, [held.driver_id] if held else [])
    other = db.get(Vehicle, his.vehicle_id) if his else None
    if held is not None and held.driver_id == driver.id:
        modes = []  # he holds it already
    elif held is not None and his is not None:
        modes = ["swap", "release"]
    elif held is not None or his is not None:
        modes = ["release"]
    else:
        modes = ["handover"]
    return {
        "holder": None
        if held is None
        else {"driver": names.get(held.driver_id), "custody_id": str(held.public_id), "since": held.started_at},
        "driver_vehicle": None
        if his is None
        else {
            "id": str(other.public_id),
            "plate_number": other.plate_number,
            "custody_id": str(his.public_id),
            "since": his.started_at,
            "last_odometer_km": other.last_odometer_km,
        },
        "modes_allowed": modes,
    }


def transfer(
    db: Session,
    *,
    vehicle_public_id,
    driver_public_id,
    mode: str,
    odometer_km: int,
    photo_sha256: str,
    photos: list[dict] | None,
    started_at: datetime | None,
    other_odometer_km: int | None,
    other_photo_sha256: str | None,
    other_photos: list[dict] | None,
    note: str | None,
    actor_user_id: int,
    **scope,
) -> dict:
    """The car X handed to the driver A in one step, at one moment, when X is held by B or A holds Y.
    release: B (if any) leaves X, A gives Y back (if he holds one; Y becomes available), A takes X.
    swap: B and A exchange: B takes Y, A takes X.
    One reading per car serves its return and its handover. Everything is locked first: the open custodies (the
    order return_vehicle locks in: the custody, then the vehicle), then both vehicles in id order."""
    at = started_at or utcnow()
    _check_moment(at)
    target = _get_vehicle(db, vehicle_public_id, **scope)
    driver = people.ref_by_public_id(db, driver_public_id, **scope)
    held = list(
        db.scalars(
            select(Custody)
            .where(or_(Custody.vehicle_id == target.id, Custody.driver_id == driver.id), Custody.ended_at.is_(None))
            .order_by(Custody.id)
            .with_for_update()
        )
    )
    on_x = next((c for c in held if c.vehicle_id == target.id), None)  # B's custody of X
    on_y = next((c for c in held if c.driver_id == driver.id and c.vehicle_id != target.id), None)  # A's of Y
    if on_x is not None and on_x.driver_id == driver.id:
        raise AppError(409, "transfer_same_driver")
    if mode == "swap" and (on_x is None or on_y is None):
        raise AppError(422, "swap_needs_two_cars")
    if on_y is not None:
        if not _in_scope(on_y.company_id, **scope):
            raise AppError(403, "company_out_of_scope")
        if other_odometer_km is None or other_photo_sha256 is None:
            raise AppError(422, "other_reading_required")
    for c in (on_x, on_y):
        if c is not None and at <= c.started_at:
            raise AppError(422, "ended_before_start")
    ending = [c.id for c in (on_x, on_y) if c is not None]
    if ending and db.scalar(
        select(OdometerReading.id).where(OdometerReading.custody_id.in_(ending), OdometerReading.recorded_at > at)
    ):
        raise AppError(422, "transfer_before_last_reading")  # a custody cannot end before what was recorded in it
    ids = sorted({target.id} | ({on_y.vehicle_id} if on_y else set()))
    locked = {
        v.id: v for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(ids)).order_by(Vehicle.id).with_for_update())
    }
    x, y = locked[target.id], locked[on_y.vehicle_id] if on_y else None
    other = people.ref(db, on_x.driver_id) if on_x else None  # B
    # the drivers who take a car: the normal checks (X and Y are freed in this same transaction)
    _check_can_take(db, x, driver, at)
    if mode == "swap":
        _check_can_take(db, y, other, at)
    for sha in [photo_sha256, *(p["sha256"] for p in photos or ())]:
        _check_photo(db, sha)
    if on_y is not None:
        for sha in [other_photo_sha256, *(p["sha256"] for p in other_photos or ())]:
            _check_photo(db, sha)

    ended, started = [], []
    x_return = y_return = None
    if on_x is not None:
        out, x_return = _end_custody(db, on_x, x, at, odometer_km, photo_sha256, actor_user_id, photos)
        ended.append(out)
    if on_y is not None:
        out, y_return = _end_custody(
            db, on_y, y, at, other_odometer_km, other_photo_sha256, actor_user_id, other_photos
        )
        ended.append(out)
    moves = [(x, driver, odometer_km, photo_sha256, photos, x_return)]
    if mode == "swap":
        moves.append((y, other, other_odometer_km, other_photo_sha256, other_photos, y_return))
    for vehicle, taker, km, sha, pics, pair in moves:
        custody = _start_custody(
            db,
            vehicle,
            taker,
            started_at=at,
            kind="normal",
            reason=None,
            odometer_km=km,
            photo_sha256=sha,
            handed_over_by=actor_user_id,
            by_user=actor_user_id,
            photos=pics,
            pair=pair,
        )
        out = _custodies_out(db, [custody])[0]
        audit.record(
            db,
            action="custody.started",
            entity_type="custody",
            entity_id=custody.public_id,
            actor_user_id=actor_user_id,
            company_id=vehicle.company_id,
            after=out | {"odometer_km": km, "transfer": mode, "note": note},
        )
        started.append(out)
        if taker.id == driver.id:
            notifications.notify_driver(db, driver.id, "vehicle_handed_over", params={"plate": x.plate_number})
    if other is not None:
        if mode == "swap":
            notifications.notify_driver(
                db, other.id, "vehicle_swapped", params={"from": x.plate_number, "to": y.plate_number}
            )
        else:
            notifications.notify_driver(db, other.id, "vehicle_taken", params={"plate": x.plate_number})
    db.commit()
    return {"mode": mode, "started": started, "ended": ended}


# ------------------------------------------------------------------ maintenance centers (in the caller's transaction)


def _vehicle_for_update(db: Session, vehicle_id: int) -> Vehicle:
    return db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id).with_for_update())


def received_for_maintenance(
    db: Session, vehicle_id: int, *, odometer_km: int, photo_sha256: str, at: datetime, actor_user_id: int
) -> CustodyRef | None:
    """A maintenance center received the vehicle. The driver left it there, so an open custody ends at that moment
    with the center's reading (tracking stops with it); otherwise the reading is recorded on its own. The vehicle
    is "in maintenance" until it is picked up. Returns the custody that ended, if any."""
    _check_moment(at)
    _check_photo(db, photo_sha256)
    # the custody first, then the vehicle: the same order as return_vehicle, so the two never deadlock
    custody = db.scalar(
        select(Custody).where(Custody.vehicle_id == vehicle_id, Custody.ended_at.is_(None)).with_for_update()
    )
    vehicle = _vehicle_for_update(db, vehicle_id)
    if custody is not None:
        if at <= custody.started_at:
            raise AppError(422, "ended_before_start")
        _end_custody(db, custody, vehicle, at, odometer_km, photo_sha256, actor_user_id)
    else:
        _add_reading(
            db,
            vehicle,
            None,
            kind="maintenance_in",
            value_km=odometer_km,
            photo_sha256=photo_sha256,
            recorded_at=at,
            by_user=actor_user_id,
        )
    vehicle.status = "maintenance"
    vehicle.version += 1
    return _cref(custody) if custody is not None else None


def maintenance_reading(
    db: Session, vehicle_id: int, *, odometer_km: int, photo_sha256: str, at: datetime, actor_user_id: int
) -> None:
    """The center's reading at the end of the repair: the next handover is compared with it, not with the
    reception (a test drive is not distance off duty)."""
    _check_moment(at)
    _check_photo(db, photo_sha256)
    vehicle = _vehicle_for_update(db, vehicle_id)
    _add_reading(
        db,
        vehicle,
        None,
        kind="maintenance_out",
        value_km=odometer_km,
        photo_sha256=photo_sha256,
        recorded_at=at,
        by_user=actor_user_id,
    )
    vehicle.version += 1


def released_from_maintenance(db: Session, vehicle_id: int) -> None:
    """Picked up from the center: available again for a handover."""
    vehicle = _vehicle_for_update(db, vehicle_id)
    if vehicle.status == "maintenance":
        vehicle.status = "available"
        vehicle.version += 1


# ------------------------------------------------------------------ accidents (in the caller's transaction)


def mark_accident(db: Session, vehicle_id: int) -> bool:
    """An accident was reported: the vehicle is "in an accident" and cannot be handed over normally until it is
    repaired or the accident is closed. A vehicle already at a center or inactive keeps its status."""
    vehicle = _vehicle_for_update(db, vehicle_id)
    if vehicle.status not in ("available", "assigned"):
        return False
    vehicle.status = "accident"
    vehicle.version += 1
    return True


def clear_accident(db: Session, vehicle_id: int) -> None:
    """The accident was closed or cancelled while the vehicle was still "in an accident": back to its driver if
    someone still holds it, otherwise available."""
    vehicle = _vehicle_for_update(db, vehicle_id)
    if vehicle.status != "accident":
        return
    held = db.scalar(select(Custody.id).where(Custody.vehicle_id == vehicle_id, Custody.ended_at.is_(None)))
    vehicle.status = "assigned" if held else "available"
    vehicle.version += 1


def custody_ref_at(db: Session, vehicle_id: int, at: datetime) -> CustodyRef | None:
    """The custody that covered the vehicle at time `at`: the driver responsible then (accidents, fines)."""
    custody = db.scalar(
        select(Custody).where(
            Custody.vehicle_id == vehicle_id,
            Custody.started_at <= at,
            or_(Custody.ended_at.is_(None), Custody.ended_at > at),
        )
    )
    return None if custody is None else _cref(custody)


def list_custodies(
    db: Session,
    *,
    all_companies: bool,
    company_ids: Iterable[int],
    vehicle_public_id=None,
    driver_id: int | None = None,
    open_only: bool = False,
    needs_review: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    q = _scoped(select(Custody), Custody, all_companies, company_ids)
    if vehicle_public_id is not None:
        q = q.join(Vehicle, Vehicle.id == Custody.vehicle_id).where(Vehicle.public_id == vehicle_public_id)
    if driver_id is not None:
        q = q.where(Custody.driver_id == driver_id)
    if open_only:
        q = q.where(Custody.ended_at.is_(None))
    if needs_review is not None:
        q = q.where(Custody.needs_review.is_(needs_review))
    q = q.order_by(Custody.started_at.desc()).limit(min(limit, 200)).offset(offset)
    return _custodies_out(db, list(db.scalars(q)))


def get_custody(db: Session, public_id, **scope) -> dict:
    custody = db.scalar(_scoped(select(Custody).where(Custody.public_id == public_id), Custody, **scope))
    if custody is None:
        raise AppError(404, "custody_not_found")
    readings = db.scalars(
        select(OdometerReading).where(OdometerReading.custody_id == custody.id).order_by(OdometerReading.recorded_at)
    )
    return _custodies_out(db, [custody])[0] | {
        "readings": _readings_out(db, list(readings)),
        "photos": _photos_out(db, custody.id),
    }


def custody_at(db: Session, vehicle_public_id, at: datetime, **scope) -> dict:
    """Who was responsible for the vehicle at time `at` (fines, accidents, damage)."""
    vehicle = _get_vehicle(db, vehicle_public_id, **scope)
    custody = db.scalar(
        select(Custody).where(
            Custody.vehicle_id == vehicle.id,
            Custody.started_at <= at,
            or_(Custody.ended_at.is_(None), Custody.ended_at > at),
        )
    )
    if custody is None:
        raise AppError(404, "no_custody_at_time")
    return _custodies_out(db, [custody])[0]


def review_custody(db: Session, public_id, *, note: str, actor_user_id: int, **scope) -> dict:
    custody = db.scalar(
        _scoped(select(Custody).where(Custody.public_id == public_id), Custody, **scope).with_for_update()
    )
    if custody is None:
        raise AppError(404, "custody_not_found")
    if not custody.needs_review:
        raise AppError(409, "nothing_to_review")
    custody.needs_review = False
    audit.record(
        db,
        action="custody.reviewed",
        entity_type="custody",
        entity_id=custody.public_id,
        actor_user_id=actor_user_id,
        company_id=custody.company_id,
        after={"note": note},
    )
    db.commit()
    return _custodies_out(db, [custody])[0]


def flag_departed_driver(db: Session, employee: people.EmployeeRef) -> None:
    """Employment ended while the driver still holds a vehicle: someone must collect it."""
    custody = db.scalar(select(Custody).where(Custody.driver_id == employee.id, Custody.ended_at.is_(None)))
    if custody is None:
        return
    vehicle = db.get(Vehicle, custody.vehicle_id)
    notifications.raise_alert(
        db,
        "driver_left_with_vehicle",
        company_id=custody.company_id,
        entity_type="custody",
        entity_id=custody.public_id,
        params={"driver": employee.name, "plate": vehicle.plate_number},
        dedupe_key=f"driver_left:{custody.id}",
    )
    db.commit()


# ------------------------------------------------------------------ for other modules


def vehicle_ref_by_public_id(db: Session, public_id, **scope) -> VehicleRef:
    return _vref(_get_vehicle(db, public_id, **scope))


def vehicle_by_plate(db: Session, plate: str) -> VehicleRef | None:
    """Matches the way plates are unique: ignoring spaces and letter case."""
    key = "".join(plate.upper().split())
    vehicle = db.scalar(
        select(Vehicle).where(func.upper(func.regexp_replace(Vehicle.plate_number, r"\s", "", "g")) == key)
    )
    return None if vehicle is None else _vref(vehicle)


def vehicle_by_vin(db: Session, vin: str) -> VehicleRef | None:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.vin == vin.strip().upper()))
    return None if vehicle is None else _vref(vehicle)


def vehicle_version(db: Session, vehicle_id: int) -> int:
    return db.scalar(select(Vehicle.version).where(Vehicle.id == vehicle_id))


def holder(db: Session, vehicle_id: int) -> int | None:
    """The driver holding the vehicle now, if any."""
    return db.scalar(select(Custody.driver_id).where(Custody.vehicle_id == vehicle_id, Custody.ended_at.is_(None)))


def vehicles(db: Session, ids: Iterable[int]) -> dict[int, VehicleRef]:
    ids = set(ids)
    if not ids:
        return {}
    return {v.id: _vref(v) for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(ids)))}


def vehicle_cards(db: Session, ids: Iterable[int]) -> dict[int, dict]:
    """How other modules' screens show a vehicle (a maintenance center needs make and model, not just the plate)."""
    ids = set(ids)
    if not ids:
        return {}
    return {
        v.id: {
            "id": str(v.public_id),
            "plate_number": v.plate_number,
            "make": v.make,
            "model": v.model,
            "year": v.year,
            "color": v.color,
            "status": v.status,
        }
        for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(ids)))
    }


def plate_numbers(db: Session, ids: Iterable[int]) -> dict[int, str]:
    ids = set(ids)
    if not ids:
        return {}
    return dict(db.execute(select(Vehicle.id, Vehicle.plate_number).where(Vehicle.id.in_(ids))).all())


def custody_ref_by_public_id(db: Session, public_id, **scope) -> CustodyRef:
    custody = db.scalar(_scoped(select(Custody).where(Custody.public_id == public_id), Custody, **scope))
    if custody is None:
        raise AppError(404, "custody_not_found")
    return _cref(custody)


def open_custody_for_driver(db: Session, driver_id: int) -> CustodyRef | None:
    custody = db.scalar(select(Custody).where(Custody.driver_id == driver_id, Custody.ended_at.is_(None)))
    return None if custody is None else _cref(custody)


def custodies_for_driver(db: Session, driver_id: int, start: datetime, end: datetime) -> list[CustodyRef]:
    """The driver's custody periods that overlap [start, end]."""
    q = select(Custody).where(
        Custody.driver_id == driver_id,
        Custody.started_at <= end,
        or_(Custody.ended_at.is_(None), Custody.ended_at > start),
    )
    return [_cref(c) for c in db.scalars(q.order_by(Custody.started_at))]


def open_custodies(db: Session) -> list[CustodyRef]:
    return [_cref(c) for c in db.scalars(select(Custody).where(Custody.ended_at.is_(None)))]


def driver_today(db: Session, employee_id: int) -> dict:
    """What the driver app shows on its home screen."""
    custody = db.scalar(select(Custody).where(Custody.driver_id == employee_id, Custody.ended_at.is_(None)))
    if custody is None:
        return {"custody": None, "start_day_done": False, "end_day_done": False, "sessions": 0, "recent": {}}
    vehicle = db.get(Vehicle, custody.vehicle_id)
    first = today() - timedelta(days=RECENT_DAYS)
    days = driver_days(db, employee_id, first, today())
    day = days.get(today())
    last = day["sessions"][-1] if day else None  # he may start again after ending the day
    if last is None and (yesterday := days.get(today() - timedelta(days=1))):
        # a night shift: yesterday's last session, still open within a day, is the one he ends now
        night = yesterday["sessions"][-1]
        if night["end"] is None and night["start"]["recorded_at"] > utcnow() - SESSION_HOLDS:
            last = night
    started = last is not None and last["start"]["custody_id"] == custody.id
    return {
        "custody": {
            "id": str(custody.public_id),
            "plate_number": vehicle.plate_number,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "started_at": custody.started_at,
            "last_odometer_km": vehicle.last_odometer_km,
        },
        "start_day_done": started,
        "end_day_done": started and last["end"] is not None,
        # the open (or last) session's start: when and at what reading his day started
        "day_started_at": last["start"]["recorded_at"] if started else None,
        "day_start_km": last["start"]["km"] if started else None,
        "sessions": len(day["sessions"]) if day else 0,
        # the days before, for a report sent late: how many sessions each had
        "recent": {d.isoformat(): len(x["sessions"]) for d, x in days.items() if d < today()},
    }


def _brief(r: OdometerReading) -> dict:
    return {
        "id": str(r.public_id),
        "kind": r.kind,
        "km": r.effective_km,
        "recorded_at": r.recorded_at,
        "flags": list(r.flags),
        "custody_id": r.custody_id,
        "photo_sha256": r.photo_sha256,
    }


DAY_CLOSES_WITHIN = timedelta(hours=24)
RECENT_DAYS = 2  # a report may be sent up to two days late (daily_ops MAX_DAYS_BACK)
SESSION_HOLDS = timedelta(hours=16)  # longer than any shift: a session open longer was forgotten


def driver_days(db: Session, employee_id: int, first, last) -> dict:
    """Each business day from first to last the driver started, as its work sessions: each start-of-day reading
    with the reading that closed it (his end of day, or the vehicle returned, on the same custody, within 24 hours
    and before his next start) and the distance between them (BRD FR-DWR-02/05). He may start again after ending
    the day; the day's start is its first, its end the last session's close (None while that one is open), its
    distance the sum of the closed sessions."""
    starts = list(
        db.scalars(
            select(OdometerReading)
            .where(
                OdometerReading.driver_id == employee_id,
                OdometerReading.kind == "start_day",
                OdometerReading.business_date.between(first, last),
            )
            .order_by(OdometerReading.recorded_at)
        )
    )
    if not starts:
        return {}
    later_start = db.scalar(
        select(func.min(OdometerReading.recorded_at)).where(
            OdometerReading.driver_id == employee_id,
            OdometerReading.kind == "start_day",
            OdometerReading.recorded_at > starts[-1].recorded_at,
        )
    )
    closes = list(
        db.scalars(
            select(OdometerReading)
            .where(
                OdometerReading.driver_id == employee_id,
                OdometerReading.kind.in_(("end_day", "return")),
                OdometerReading.recorded_at > starts[0].recorded_at,
                OdometerReading.recorded_at <= starts[-1].recorded_at + DAY_CLOSES_WITHIN,
            )
            .order_by(OdometerReading.recorded_at)
        )
    )
    out = {}
    for start, until in zip(starts, [s.recorded_at for s in starts[1:]] + [later_start], strict=True):
        limit = min(start.recorded_at + DAY_CLOSES_WITHIN, until or start.recorded_at + DAY_CLOSES_WITHIN)
        end = next(
            (c for c in closes if c.custody_id == start.custody_id and start.recorded_at < c.recorded_at <= limit),
            None,
        )
        out.setdefault(start.business_date, []).append(
            {
                "start": _brief(start),
                "end": _brief(end) if end else None,
                "km": end.effective_km - start.effective_km if end else None,
            }
        )
    return {
        day: {
            "start": sessions[0]["start"],
            "end": sessions[-1]["end"],
            "km": sum(kms) if (kms := [s["km"] for s in sessions if s["km"] is not None]) else None,
            "sessions": sessions,
        }
        for day, sessions in out.items()
    }


def work_periods(db: Session, vehicle_id: int, start: datetime, end: datetime) -> list[tuple[int, datetime, datetime]]:
    """The work days driven in this vehicle that overlap [start, end), as (custody, from, to): from a start of day to
    the reading that closed it (his end of day or the return, on the same custody, within 24 hours and before his
    next start, as driver_days pairs them), or to 24 hours later, or now (BRD FR-TRK-09). The vehicle's movement
    outside them, in custody but before the day started or after it ended, is off duty."""
    readings = db.scalars(
        select(OdometerReading)
        .where(
            OdometerReading.vehicle_id == vehicle_id,
            OdometerReading.kind.in_(("start_day", "end_day", "return")),
            OdometerReading.recorded_at > start - DAY_CLOSES_WITHIN,
            OdometerReading.recorded_at < end,
        )
        .order_by(OdometerReading.recorded_at, OdometerReading.id)
    )
    now, periods, opened = utcnow(), [], None
    for r in readings:
        if r.kind == "start_day":
            if opened is not None:  # never closed: the next start ends it
                periods.append(
                    (opened.custody_id, opened.recorded_at, min(r.recorded_at, opened.recorded_at + DAY_CLOSES_WITHIN))
                )
            opened = r
        elif (
            opened is not None
            and r.custody_id == opened.custody_id
            and r.recorded_at <= opened.recorded_at + DAY_CLOSES_WITHIN
        ):
            periods.append((opened.custody_id, opened.recorded_at, r.recorded_at))
            opened = None
    if opened is not None:
        periods.append((opened.custody_id, opened.recorded_at, min(opened.recorded_at + DAY_CLOSES_WITHIN, now)))
    return [p for p in periods if p[2] > start and p[1] < end]


def on_duty_now(db: Session, custody_ids: Iterable[int]) -> set[int]:
    """The custodies whose driver has started his day and not ended it, now (within 24 hours of the start)."""
    ids = list(custody_ids)
    if not ids:
        return set()
    now = utcnow()
    last = (
        select(OdometerReading.custody_id, OdometerReading.kind, OdometerReading.recorded_at)
        .where(
            OdometerReading.custody_id.in_(ids),
            OdometerReading.kind.in_(("start_day", "end_day", "return")),
            OdometerReading.recorded_at > now - DAY_CLOSES_WITHIN,
        )
        .order_by(OdometerReading.custody_id, OdometerReading.recorded_at.desc(), OdometerReading.id.desc())
        .distinct(OdometerReading.custody_id)
    )
    return {c for c, kind, _ in db.execute(last) if kind == "start_day"}


def held_days(db: Session, driver_ids: Iterable[int], first, last) -> dict[int, set]:
    """The Kuwait days, first to last inclusive, on which each driver held a vehicle for any part of the day."""
    ids = list(driver_ids)
    out: dict[int, set] = {i: set() for i in ids}
    if not ids:
        return out
    start = datetime.combine(first, datetime.min.time(), tzinfo=KUWAIT)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=KUWAIT)
    q = select(Custody.driver_id, Custody.started_at, Custody.ended_at).where(
        Custody.driver_id.in_(ids), Custody.started_at < end, or_(Custody.ended_at.is_(None), Custody.ended_at > start)
    )
    now = utcnow()
    for driver_id, started, ended in db.execute(q):
        day, stop = max(business_date(started), first), min(business_date(ended or now), last)
        while day <= stop:
            out[driver_id].add(day)
            day += timedelta(days=1)
    return out


def start_days(db: Session, employee_ids: Iterable[int], first, last) -> dict[int, set]:
    """The days each driver started in the app (a start-of-day odometer reading), first to last inclusive."""
    ids = list(employee_ids)
    out: dict[int, set] = {i: set() for i in ids}
    if not ids:
        return out
    q = select(OdometerReading.driver_id, OdometerReading.business_date).where(
        OdometerReading.kind == "start_day",
        OdometerReading.driver_id.in_(ids),
        OdometerReading.business_date.between(first, last),
    )
    for driver_id, day in db.execute(q):
        out[driver_id].add(day)
    return out


def drivers_started(db: Session, day) -> dict[int, int]:
    """The drivers who started that business day (a start-of-day reading), with how many times (he may start again
    after ending it): they owe that day's report, one per session."""
    return dict(
        db.execute(
            select(OdometerReading.driver_id, func.count())
            .where(
                OdometerReading.kind == "start_day",
                OdometerReading.business_date == day,
                OdometerReading.driver_id.is_not(None),
            )
            .group_by(OdometerReading.driver_id)
        ).all()
    )


# ------------------------------------------------------------------ the driver's vehicle (BRD FR-APP-02, FR-ASG-04)


def _change_out(r: VehicleChangeRequest | None, plates: dict | None = None, names: dict | None = None) -> dict | None:
    if r is None:
        return None
    return {
        "id": str(r.public_id),
        "status": r.status,
        "reason": r.reason,
        "note": r.note,
        "created_at": r.created_at,
        "decided_at": r.decided_at,
        "requested_plate": r.requested_plate,
        "vehicle_plate": (plates or {}).get(r.vehicle_id),
        "driver": (names or {}).get(r.employee_id),
    }


def _plate_key(plate: str) -> str:
    """A plate as the driver may type it, compared: separators (spaces, dashes, slashes) ignored."""
    return re.sub(r"[\s/-]", "", normalize_plate(plate))


def _vehicle_for_change(db: Session, plate: str, company_id: int) -> Vehicle | None:
    """His company's vehicle with that plate: the same plate first; else the only one equal ignoring separators
    ("12-34567" for "12 34567" or "1234567"). Another company's vehicle is not found."""
    exact = vehicle_by_plate(db, plate)
    if exact is not None:
        return db.get(Vehicle, exact.id) if exact.company_id == company_id else None
    key = func.upper(
        func.regexp_replace(func.translate(Vehicle.plate_number, _PLATE_FROM, _PLATE_TO), r"[\s/-]", "", "g")
    )
    found = list(db.scalars(select(Vehicle).where(key == _plate_key(plate), Vehicle.company_id == company_id).limit(2)))
    return found[0] if len(found) == 1 else None


def _requested_vehicles(db: Session, rows: list[VehicleChangeRequest]) -> dict[int, dict]:
    """The cars asked for, as they are now: their status and who holds them."""
    vehicles = {
        v.id: v
        for v in db.scalars(select(Vehicle).where(Vehicle.id.in_({r.requested_vehicle_id for r in rows} - {None})))
    }
    open_ = _open_custodies_by_vehicle(db, list(vehicles))
    holders = people.names(db, [c.driver_id for c in open_.values()])
    return {
        v.id: {
            "found": True,
            "id": str(v.public_id),
            "plate": v.plate_number,
            "status": v.status,
            "holder": holders.get(open_[v.id].driver_id) if v.id in open_ else None,
        }
        for v in vehicles.values()
    }


def driver_vehicle(db: Session, employee_id: int) -> dict:
    """ "My car" in the app: the vehicle held, its last odometer reading, its registration's expiry, and the change
    he asked for, if any; without a car, the one he registered (waiting for the office, or refused)."""
    custody = db.scalar(select(Custody).where(Custody.driver_id == employee_id, Custody.ended_at.is_(None)))
    if custody is None:
        return {"vehicle": None, "change_request": None, "claim": _my_claim(db, employee_id)}
    vehicle = db.get(Vehicle, custody.vehicle_id)
    last = db.scalar(
        select(OdometerReading)
        .where(OdometerReading.vehicle_id == vehicle.id)
        .order_by(OdometerReading.recorded_at.desc(), OdometerReading.id.desc())
        .limit(1)
    )
    _, registration = documents.current_expiry(db, "registration", "vehicle", vehicle.id)
    request = db.scalar(
        select(VehicleChangeRequest)
        .where(VehicleChangeRequest.custody_id == custody.id)
        .order_by(VehicleChangeRequest.id.desc())
        .limit(1)
    )
    return {
        "vehicle": {
            "plate_number": vehicle.plate_number,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "color": vehicle.color,
            "since": custody.started_at,
            "last_odometer_km": last.effective_km if last else vehicle.last_odometer_km,
            "last_reading_at": last.recorded_at if last else None,
            "registration_expiry": registration,
        },
        "change_request": _change_out(request),
        "claim": _my_claim(db, employee_id),
    }


def request_vehicle_change(db: Session, *, employee_id: int, device_id: int, requested_plate: str, reason: str) -> dict:
    """The driver asks for another vehicle, naming it by its plate, with his reason; the supervisors see it
    (FR-ASG-04). The plate must be one of his company's vehicles: a plate not found is refused so he types it again."""
    custody = db.scalar(
        select(Custody).where(Custody.driver_id == employee_id, Custody.ended_at.is_(None)).with_for_update()
    )
    if custody is None:
        raise AppError(409, "no_open_custody")
    requested = _vehicle_for_change(db, requested_plate, custody.company_id)
    if requested is None:
        raise AppError(422, "vehicle_plate_not_found")
    if requested.id == custody.vehicle_id:
        raise AppError(422, "vehicle_change_same_vehicle")
    request = VehicleChangeRequest(
        employee_id=employee_id,
        company_id=custody.company_id,
        custody_id=custody.id,
        vehicle_id=custody.vehicle_id,
        requested_plate=requested.plate_number,
        requested_vehicle_id=requested.id,
        reason=reason,
        created_by_device=device_id,
    )
    try:
        with db.begin_nested():
            db.add(request)
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "vehicle_change_requests_one_pending_idx":
            raise AppError(409, "vehicle_change_exists") from None
        raise
    driver = people.ref(db, employee_id)
    vehicle = db.get(Vehicle, custody.vehicle_id)
    notifications.raise_alert(
        db,
        "vehicle_change_requested",
        company_id=custody.company_id,
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        params={
            "driver": driver.name,
            "plate": vehicle.plate_number,
            "requested": requested.plate_number,
            "reason": reason,
        },
        dedupe_key=f"vehicle_change:{request.id}",
    )
    audit.record(
        db,
        action="vehicle_change.requested",
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        actor_type="device",
        company_id=custody.company_id,
        after={
            "driver": str(driver.public_id),
            "requested_plate": requested.plate_number,
            "requested_vehicle": str(requested.public_id),
            "reason": reason,
        },
    )
    db.commit()
    return driver_vehicle(db, employee_id)


def vehicle_change_requests(
    db: Session,
    *,
    status: str | None = "pending",
    driver_id: int | None = None,
    vehicle_id: int | None = None,
    limit: int = 500,
    offset: int = 0,
    all_companies: bool,
    company_ids,
) -> list:
    """The office's list: the pending ones oldest first (the queue), or every request (status "all" or empty) newest
    first, with the car asked for as it is now and who closed it. vehicle_id matches the car held or the one asked
    for."""
    if status == "all":
        status = None
    q = select(VehicleChangeRequest).order_by(
        VehicleChangeRequest.created_at if status == "pending" else VehicleChangeRequest.created_at.desc(),
        VehicleChangeRequest.id if status == "pending" else VehicleChangeRequest.id.desc(),
    )
    if status:
        q = q.where(VehicleChangeRequest.status == status)
    if driver_id is not None:
        q = q.where(VehicleChangeRequest.employee_id == driver_id)
    if vehicle_id is not None:
        q = q.where(
            or_(VehicleChangeRequest.vehicle_id == vehicle_id, VehicleChangeRequest.requested_vehicle_id == vehicle_id)
        )
    if not all_companies:
        q = q.where(VehicleChangeRequest.company_id.in_(list(company_ids)))
    rows = list(db.scalars(q.limit(limit).offset(offset)))
    plates = plate_numbers(db, {r.vehicle_id for r in rows})
    public = dict(
        db.execute(select(Vehicle.id, Vehicle.public_id).where(Vehicle.id.in_({r.vehicle_id for r in rows}))).all()
    )
    names = people.names(db, {r.employee_id for r in rows})
    requested = _requested_vehicles(db, rows)
    users = identity.user_names(db, {r.decided_by for r in rows} - {None})
    out = []
    for r in rows:
        item = _change_out(r, plates, names)
        item["vehicle_id"] = str(public[r.vehicle_id])
        item["requested_vehicle"] = requested.get(r.requested_vehicle_id) or (
            {"found": False, "plate": r.requested_plate} if r.requested_plate else None
        )
        item["decided_by"] = users.get(r.decided_by)
        out.append(item)
    return out


def _decide_change(db: Session, r: VehicleChangeRequest, status: str, actor_user_id: int, note: str | None) -> None:
    r.status, r.decided_by, r.decided_at, r.note = status, actor_user_id, utcnow(), note
    notifications.resolve(db, f"vehicle_change:{r.id}")
    plate = db.get(Vehicle, r.vehicle_id).plate_number
    if status == "done":
        notifications.notify_driver(db, r.employee_id, "vehicle_change_done", params={"plate": plate})
    else:
        notifications.notify_driver(
            db, r.employee_id, "vehicle_change_rejected", params={"plate": plate, "reason": note or ""}
        )


def _close_change_request(db: Session, custody: Custody, vehicle: Vehicle, actor_user_id: int) -> None:
    """The vehicle returned: the change the driver asked for is done."""
    pending = db.scalar(
        select(VehicleChangeRequest).where(
            VehicleChangeRequest.custody_id == custody.id, VehicleChangeRequest.status == "pending"
        )
    )
    if pending is not None:
        _decide_change(db, pending, "done", actor_user_id, None)


def close_vehicle_change(
    db: Session, public_id, *, done: bool, note: str | None, actor_user_id: int, all_companies: bool, company_ids
) -> dict:
    """The supervisor closes the request: done (handled another way), or refused with the note the driver reads."""
    r = db.scalar(select(VehicleChangeRequest).where(VehicleChangeRequest.public_id == public_id).with_for_update())
    if r is None or not (all_companies or r.company_id in set(company_ids)):
        raise AppError(404, "vehicle_change_not_found")
    if r.status != "pending":
        raise AppError(409, "vehicle_change_decided")
    if not done and not note:
        raise AppError(422, "reason_required")
    _decide_change(db, r, "done" if done else "rejected", actor_user_id, note)
    audit.record(
        db,
        action="vehicle_change.done" if done else "vehicle_change.rejected",
        entity_type="vehicle",
        entity_id=db.get(Vehicle, r.vehicle_id).public_id,
        actor_user_id=actor_user_id,
        company_id=r.company_id,
        after={"note": note},
    )
    db.commit()
    plates = plate_numbers(db, {r.vehicle_id})
    return _change_out(r, plates, people.names(db, {r.employee_id}))


# ------------------------------------------------------------------ a car the driver registers from the app


def _claim_photos(photos: Iterable) -> list[dict]:
    """Condition photos as the app sends them (a sha256 each) or with their position: [{position, sha256}]."""
    out = {}
    for p in photos or ():
        item = (
            {"position": "other", "sha256": p}
            if isinstance(p, str)
            else {"position": p["position"], "sha256": p["sha256"]}
        )
        out.setdefault(item["sha256"], item)
    return list(out.values())


def _claim_out(c: VehicleClaim, plates: dict[int, str]) -> dict:
    return {
        "id": str(c.public_id),
        "status": c.status,
        "plate": plates.get(c.vehicle_id, ""),
        "odometer_km": c.odometer_km,
        "claimed_at": c.claimed_at,
        "created_at": c.created_at,
        "note": c.note,
        "decided_at": c.decided_at,
        "photos": list(c.photos or []),
        # waiting longer than a custody may start back: it can only be refused
        "expired": c.status == "pending" and c.claimed_at < utcnow() - BACKDATE_LIMIT,
    }


def _my_claim(db: Session, employee_id: int) -> dict | None:
    """The car he registered, for the app: waiting, or decided since his last custody ended (a refusal of long ago,
    before the cars he has had since, is not shown again)."""
    claim = db.scalar(
        select(VehicleClaim).where(VehicleClaim.employee_id == employee_id).order_by(VehicleClaim.id.desc()).limit(1)
    )
    if claim is None:
        return None
    if claim.status != "pending":
        last_end = db.scalar(
            select(func.max(Custody.ended_at)).where(Custody.driver_id == employee_id, Custody.ended_at.is_not(None))
        )
        if last_end is not None and claim.decided_at is not None and last_end > claim.decided_at:
            return None
    return _claim_out(claim, plate_numbers(db, {claim.vehicle_id}))


def request_vehicle_claim(
    db: Session,
    *,
    employee_id: int,
    device_id: int,
    plate: str,
    odometer_km: int,
    photo_sha256: str,
    recorded_at: datetime,
    photos: list,
    client_ref,
) -> dict:
    """The driver, holding no car, registers the one he takes: its plate (one of his company's vehicles, free and
    available), the odometer reading and its photo from the app's camera on this phone, condition photos. It waits for
    the office; the custody starts only when approved, at the photo's time."""
    if db.scalar(select(VehicleClaim.id).where(VehicleClaim.client_ref == client_ref)):
        raise AppError(409, "vehicle_claim_exists")  # a resend: already recorded
    now = utcnow()
    if not (now - DRIVER_READING_DELAY <= recorded_at <= now + CLOCK_SKEW):
        raise AppError(422, "invalid_recorded_at")
    driver = people.ref(db, employee_id)
    if db.scalar(select(Custody.id).where(Custody.driver_id == employee_id, Custody.ended_at.is_(None))):
        raise AppError(409, "driver_has_custody")
    if db.scalar(
        select(VehicleClaim.id).where(VehicleClaim.employee_id == employee_id, VehicleClaim.status == "pending")
    ):
        raise AppError(409, "vehicle_claim_pending")
    vehicle = _vehicle_for_change(db, plate, driver.company_id)
    if vehicle is None:
        raise AppError(422, "vehicle_plate_not_found")
    if holder(db, vehicle.id) is not None:
        raise AppError(409, "vehicle_held_by_other")
    if vehicle.status != "available":
        raise AppError(409, "vehicle_not_available", status=vehicle.status)
    _check_can_take(db, vehicle, driver, recorded_at)
    condition = _claim_photos(photos)
    for sha in [photo_sha256, *(p["sha256"] for p in condition)]:
        photo = _check_photo(db, sha)
        if photo.source != "camera" or photo.uploaded_by_device != device_id:
            raise AppError(422, "photo_not_from_camera")
    claim = VehicleClaim(
        employee_id=employee_id,
        company_id=vehicle.company_id,
        vehicle_id=vehicle.id,
        odometer_km=odometer_km,
        photo_sha256=photo_sha256,
        photos=condition,
        claimed_at=recorded_at,
        client_ref=client_ref,
        created_by_device=device_id,
    )
    try:
        with db.begin_nested():
            db.add(claim)
            db.flush()
    except IntegrityError as exc:
        constraint = violated_constraint(exc)
        if constraint == "vehicle_claims_client_ref_key":
            raise AppError(409, "vehicle_claim_exists") from None  # a resend: already recorded
        if constraint == "vehicle_claims_one_pending_idx":
            raise AppError(409, "vehicle_claim_pending") from None  # another one waits: not this one
        raise
    notifications.raise_alert(
        db,
        "vehicle_claim_requested",
        company_id=vehicle.company_id,
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        params={"driver": driver.name, "plate": vehicle.plate_number, "km": odometer_km},
        dedupe_key=f"vehicle_claim:{claim.id}",
    )
    audit.record(
        db,
        action="vehicle_claim.requested",
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        actor_type="device",
        company_id=vehicle.company_id,
        after={"driver": str(driver.public_id), "odometer_km": odometer_km, "claimed_at": recorded_at.isoformat()},
    )
    db.commit()
    return driver_vehicle(db, employee_id)


def vehicle_claims(
    db: Session, *, status: str | None = "pending", limit: int = 200, offset: int = 0, all_companies: bool, company_ids
) -> list[dict]:
    """The office's list: the waiting ones oldest first (the queue), or every claim ("all") newest first, with the car
    as it is now (its last reading, its status, who holds it)."""
    if status == "all":
        status = None
    q = select(VehicleClaim).order_by(
        VehicleClaim.created_at if status == "pending" else VehicleClaim.created_at.desc(),
        VehicleClaim.id if status == "pending" else VehicleClaim.id.desc(),
    )
    if status:
        q = q.where(VehicleClaim.status == status)
    if not all_companies:
        q = q.where(VehicleClaim.company_id.in_(list(company_ids)))
    return _claims_out(db, list(db.scalars(q.limit(min(limit, 500)).offset(offset))))


def _claims_out(db: Session, rows: list[VehicleClaim]) -> list[dict]:
    cars = {v.id: v for v in db.scalars(select(Vehicle).where(Vehicle.id.in_({r.vehicle_id for r in rows})))}
    open_ = _open_custodies_by_vehicle(db, list(cars))
    names = people.names(db, {r.employee_id for r in rows} | {c.driver_id for c in open_.values()})
    users = identity.user_names(db, {r.decided_by for r in rows} - {None})
    custodies = dict(
        db.execute(
            select(Custody.id, Custody.public_id).where(Custody.id.in_({r.custody_id for r in rows} - {None}))
        ).all()
    )
    plates = {i: v.plate_number for i, v in cars.items()}
    out = []
    for r in rows:
        car = cars[r.vehicle_id]
        held = open_.get(car.id)
        out.append(
            _claim_out(r, plates)
            | {
                "vehicle_id": str(car.public_id),
                "driver": names.get(r.employee_id),
                "vehicle_last_km": car.last_odometer_km,
                "vehicle_status": car.status,
                "holder": names.get(held.driver_id) if held else None,
                "decided_by": users.get(r.decided_by),
                "custody_id": str(custodies[r.custody_id]) if r.custody_id else None,
            }
        )
    return out


def _claim_for_update(db: Session, public_id, all_companies: bool, company_ids) -> VehicleClaim:
    claim = db.scalar(select(VehicleClaim).where(VehicleClaim.public_id == public_id).with_for_update())
    if claim is None or not _in_scope(claim.company_id, all_companies, company_ids):
        raise AppError(404, "vehicle_claim_not_found")
    if claim.status != "pending":
        raise AppError(409, "vehicle_claim_decided")
    return claim


def claim_photo(db: Session, public_id, sha256: str | None, *, all_companies: bool, company_ids) -> files.FileInfo:
    """The claim's odometer photo (sha256 None), or one of its condition photos."""
    claim = db.scalar(select(VehicleClaim).where(VehicleClaim.public_id == public_id))
    if claim is None or not _in_scope(claim.company_id, all_companies, company_ids):
        raise AppError(404, "vehicle_claim_not_found")
    if sha256 is None:
        return files.get(db, claim.photo_sha256)
    if sha256 not in {p["sha256"] for p in claim.photos or ()}:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def approve_vehicle_claim(db: Session, public_id, *, actor_user_id: int, all_companies: bool, company_ids) -> dict:
    """A normal handover from the claim: its reading, photos and time, with the checks of that moment. A car taken
    meanwhile (or a driver who got one) is refused and the claim stays waiting, for the office to refuse it."""
    claim = _claim_for_update(db, public_id, all_companies, company_ids)
    if claim.claimed_at < utcnow() - BACKDATE_LIMIT:
        raise AppError(409, "vehicle_claim_expired")  # a custody is not started that far back
    vehicle = _vehicle_for_update(db, claim.vehicle_id)
    driver = people.ref(db, claim.employee_id)
    if holder(db, vehicle.id) is not None:
        raise AppError(409, "vehicle_has_custody")
    # the custody would start back at the claim's time: nothing may have happened to the car, nor to the driver's
    # custodies, since then (a reading, a custody begun or ended)
    after = claim.claimed_at
    if db.scalar(
        select(OdometerReading.id).where(OdometerReading.vehicle_id == vehicle.id, OdometerReading.recorded_at > after)
    ) or db.scalar(
        select(Custody.id).where(
            Custody.vehicle_id == vehicle.id, or_(Custody.started_at > after, Custody.ended_at > after)
        )
    ):
        raise AppError(409, "vehicle_changed_since_claim")
    if db.scalar(
        select(Custody.id).where(
            Custody.driver_id == driver.id, or_(Custody.started_at > after, Custody.ended_at > after)
        )
    ):
        raise AppError(409, "vehicle_claim_stale")
    _check_can_take(db, vehicle, driver, claim.claimed_at)
    custody = _start_custody(
        db,
        vehicle,
        driver,
        started_at=claim.claimed_at,
        kind="normal",
        reason=None,
        odometer_km=claim.odometer_km,
        photo_sha256=claim.photo_sha256,
        handed_over_by=actor_user_id,
        by_device=claim.created_by_device,
        photos=list(claim.photos or []),
    )
    claim.decided_by = actor_user_id  # approved, linked and told as the custody started
    out = _custodies_out(db, [custody])[0]
    audit.record(
        db,
        action="custody.started",
        entity_type="custody",
        entity_id=custody.public_id,
        actor_user_id=actor_user_id,
        company_id=vehicle.company_id,
        after=out | {"odometer_km": claim.odometer_km, "claim": str(claim.public_id)},
    )
    audit.record(
        db,
        action="vehicle_claim.approved",
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        actor_user_id=actor_user_id,
        company_id=vehicle.company_id,
        after={"claim": str(claim.public_id), "custody": str(custody.public_id)},
    )
    db.commit()
    return _claim_by_id(db, claim.id)


def reject_vehicle_claim(
    db: Session, public_id, *, note: str | None, actor_user_id: int, all_companies: bool, company_ids
) -> dict:
    """Refused with the reason the driver reads; he may register a car again."""
    claim = _claim_for_update(db, public_id, all_companies, company_ids)
    if not note:
        raise AppError(422, "reason_required")
    claim.status, claim.note, claim.decided_by, claim.decided_at = "rejected", note, actor_user_id, utcnow()
    vehicle = db.get(Vehicle, claim.vehicle_id)
    notifications.resolve(db, f"vehicle_claim:{claim.id}")
    notifications.notify_driver(
        db, claim.employee_id, "vehicle_claim_rejected", params={"plate": vehicle.plate_number, "reason": note}
    )
    audit.record(
        db,
        action="vehicle_claim.rejected",
        entity_type="vehicle",
        entity_id=vehicle.public_id,
        actor_user_id=actor_user_id,
        company_id=claim.company_id,
        after={"claim": str(claim.public_id), "note": note},
    )
    db.commit()
    return _claim_by_id(db, claim.id)


def _claim_by_id(db: Session, claim_id: int) -> dict:
    return _claims_out(db, [db.get(VehicleClaim, claim_id)])[0]
