"""Vehicles, custody (which driver had which vehicle, and when) and odometer readings.

Custody periods never overlap per vehicle or per driver; the database enforces it (two exclusion constraints), so
"who was responsible for the vehicle at time T" always has at most one answer. Every reading is checked against
the previous one of the same vehicle; a suspicious reading is stored, flagged, raises an alert and waits for review.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import business_date, today, utcnow
from app.core.db import like_pattern, violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.documents import service as documents
from app.modules.files import service as files
from app.modules.fleet.models import Custody, OdometerReading, Vehicle
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

MANUAL_STATUSES = ("available", "maintenance", "accident", "inactive")  # "assigned" follows custody
VEHICLE_FIELDS = ("plate_number", "make", "model", "year", "color", "vin", "company_id", "branch_id", "status")
UNIQUE_ERRORS = {"vehicles_plate_number_idx": "plate_taken", "vehicles_vin_key": "vin_taken"}
OVERLAP_ERRORS = {"custodies_vehicle_overlap": "vehicle_has_custody", "custodies_driver_overlap": "driver_has_custody"}
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


def _vref(v: Vehicle) -> VehicleRef:
    return VehicleRef(v.id, v.public_id, v.plate_number, v.company_id, v.status)


def _cref(c: Custody) -> CustodyRef:
    return CustodyRef(c.id, c.public_id, c.vehicle_id, c.driver_id, c.company_id, c.started_at, c.ended_at, c.kind)


def normalize_plate(plate: str) -> str:
    return " ".join(plate.upper().split())


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
        db.rollback()
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


def create_vehicle(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
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
    db.commit()
    return _vehicles_out(db, [vehicle])[0]


def update_vehicle(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int, **scope) -> dict:
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
) -> OdometerReading:
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
    if db.scalar(select(func.count()).select_from(OdometerReading).where(OdometerReading.photo_sha256 == photo_sha256)):
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
        driver = (
            people.names(db, [reading.driver_id]).get(reading.driver_id, {}).get("name", "")
            if reading.driver_id
            else ""
        )
        base = {"plate": vehicle.plate_number, "driver": driver, "value": value_km, "previous": previous_km}
        alert = {
            "lower_than_previous": ("odometer_lower", base),
            "off_duty_km": ("odometer_off_duty", base | {"km": value_km - (previous_km or 0)}),
            "daily_limit": (
                "odometer_daily_limit",
                base | {"km": value_km - (previous_km or 0), "limit": settings.daily_km_alert},
            ),
            "photo_reused": ("odometer_photo_reused", base),
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
    day = business_date(recorded_at)
    if kind == "end_day" and db.scalar(
        select(OdometerReading.id).where(
            OdometerReading.custody_id == custody.id,
            OdometerReading.kind == "end_day",
            OdometerReading.business_date == day,
        )
    ):
        raise AppError(409, "reading_exists")
    try:
        with db.begin_nested():
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
    except IntegrityError as exc:
        if violated_constraint(exc) == "odometer_readings_start_day_idx":
            raise AppError(409, "reading_exists") from None
        raise
    db.commit()
    return _readings_out(db, [reading])[0]


# ------------------------------------------------------------------ custody


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
    **scope,
) -> dict:
    """An emergency handover skips the normal checks (vehicle status, driver status, expired licence), needs
    custody.emergency and a reason, and waits for review. Overlaps and ended employment are never skipped."""
    started_at = started_at or utcnow()
    _check_moment(started_at)
    vehicle = _get_vehicle(db, vehicle_public_id, lock=True, **scope)
    driver = people.ref_by_public_id(db, driver_public_id, **scope)
    if not driver.is_driver:
        raise AppError(422, "not_a_driver")
    if driver.is_terminal:
        raise AppError(422, "employment_ended")
    if kind == "emergency":
        if not can_emergency:
            raise AppError(403, "permission_denied", permission="custody.emergency")
        if not reason:
            raise AppError(422, "reason_required")
        if vehicle.status == "inactive":
            raise AppError(409, "vehicle_not_available", status=vehicle.status)
    else:
        if vehicle.status not in ("available", "assigned"):  # assigned: the overlap check gives the precise error
            raise AppError(409, "vehicle_not_available", status=vehicle.status)
        if not driver.is_working:
            raise AppError(422, "driver_not_working")
        has_license, expiry = documents.current_expiry(db, "driving_license", "employee", driver.id)
        if has_license and expiry is not None and expiry < business_date(started_at):
            raise AppError(422, "driving_license_expired", date=expiry.isoformat())
    _check_photo(db, photo_sha256)
    custody = Custody(
        vehicle_id=vehicle.id,
        driver_id=driver.id,
        company_id=vehicle.company_id,
        started_at=started_at,
        kind=kind,
        reason=reason,
        needs_review=kind == "emergency",
        handed_over_by=actor_user_id,
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
        by_user=actor_user_id,
    )
    vehicle.status = "assigned"
    vehicle.version += 1
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
    db.commit()
    return out


def return_vehicle(
    db: Session,
    public_id,
    *,
    odometer_km: int,
    photo_sha256: str,
    ended_at: datetime | None,
    actor_user_id: int,
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
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == custody.vehicle_id).with_for_update())
    custody.ended_at, custody.returned_by = ended_at, actor_user_id
    db.flush()
    _add_reading(
        db,
        vehicle,
        custody,
        kind="return",
        value_km=odometer_km,
        photo_sha256=photo_sha256,
        recorded_at=ended_at,
        by_user=actor_user_id,
    )
    if vehicle.status == "assigned":
        vehicle.status = "available"
    vehicle.version += 1
    notifications.resolve(db, f"driver_left:{custody.id}")
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
    db.commit()
    return out


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
    return _custodies_out(db, [custody])[0] | {"readings": _readings_out(db, list(readings))}


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


def vehicles(db: Session, ids: Iterable[int]) -> dict[int, VehicleRef]:
    ids = set(ids)
    if not ids:
        return {}
    return {v.id: _vref(v) for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(ids)))}


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
        return {"custody": None, "start_day_done": False}
    vehicle = db.get(Vehicle, custody.vehicle_id)
    done = db.scalar(
        select(OdometerReading.id).where(
            OdometerReading.custody_id == custody.id,
            OdometerReading.kind == "start_day",
            OdometerReading.business_date == today(),
        )
    )
    return {
        "custody": {
            "id": str(custody.public_id),
            "plate_number": vehicle.plate_number,
            "started_at": custody.started_at,
            "last_odometer_km": vehicle.last_odometer_km,
        },
        "start_day_done": done is not None,
    }
