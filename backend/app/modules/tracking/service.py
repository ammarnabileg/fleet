"""GPS tracking during custody (all day, as long as the driver holds a vehicle).

Ingest contract with the app (spec, appendix D): the app sends batches of points with a per-device sequence number;
the answer lists `stored_seqs` and `rejected` (seq + reason). The app deletes both from its queue and resends
anything else, so a lost answer never loses a point and a resent point is never stored twice.
Batches of one device are serialized (advisory lock); a device clock that is off is corrected using the time
the batch was sent. Every point must fall inside one of the driver's custody periods: it is stored against that
custody's vehicle. Mock locations are rejected and kept only as security events.
"""

import json
import math
import time
from collections.abc import AsyncIterator, Iterable
from datetime import date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import live
from app.core.clock import KUWAIT, business_date, utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people
from app.modules.tracking.models import LastPosition, MockEvent, Position, RejectedPoint
from app.modules.violations import service as violations

FUTURE_TOLERANCE = timedelta(minutes=2)
MAX_AGE = timedelta(days=7)
CLOCK_OFFSET_MIN_S = 60  # smaller differences are network delay, not a wrong clock
MAX_SPEED_ACCURACY_M = 50  # a fix less precise than this does not raise a speeding alert
MAX_ROUTE_RANGE = timedelta(days=2)
MAX_ROUTE_POINTS = 20_000
_partitions: set[date] = set()


def _month(t: datetime) -> date:
    return t.astimezone(KUWAIT).date().replace(day=1)


def ensure_partition(db: Session, month: date) -> None:
    """Remembered per process only after the caller commits: a rolled-back creation is not remembered."""
    if month not in _partitions:
        db.execute(text("SELECT tracking.ensure_month_partition(:m)"), {"m": month})


# ------------------------------------------------------------------ ingest


def _valid_point(p: dict) -> bool:
    lat, lng = p.get("lat"), p.get("lng")
    return (
        isinstance(lat, int | float)
        and isinstance(lng, int | float)
        and math.isfinite(lat)
        and math.isfinite(lng)
        and -90 <= lat <= 90
        and -180 <= lng <= 180
        and not (lat == 0 and lng == 0)
    )


def ingest(db: Session, device: identity.DevicePrincipal, *, sent_at: datetime, points: list[dict]) -> dict:
    now = utcnow()
    offset = round((now - sent_at).total_seconds())
    offset = 0 if abs(offset) < CLOCK_OFFSET_MIN_S else offset
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('tracking.ingest:' || :d, 0))"), {"d": device.device_id}
    )

    batch: dict[int, dict] = {}
    for p in points:
        batch.setdefault(p["seq"], p)
    rejected: dict[int, str] = (
        dict(
            db.execute(
                select(RejectedPoint.device_seq, RejectedPoint.reason).where(
                    RejectedPoint.device_id == device.device_id, RejectedPoint.device_seq.in_(list(batch))
                )
            ).all()
        )
        if batch
        else {}
    )

    candidates: list[tuple[int, datetime, dict]] = []
    mocks: list[tuple[int, datetime]] = []
    for seq, p in batch.items():
        if seq in rejected:
            continue
        t = p["recorded_at"] + timedelta(seconds=offset)
        if p.get("is_mock"):
            rejected[seq] = "mock"
            mocks.append((seq, t))
        elif not _valid_point(p):
            rejected[seq] = "invalid"
        elif t > now + FUTURE_TOLERANCE:
            rejected[seq] = "future"
        elif t < now - MAX_AGE:
            rejected[seq] = "too_old"
        else:
            candidates.append((seq, t, p))

    custodies = (
        fleet.custodies_for_driver(
            db, device.employee_id, min(t for _, t, _ in candidates), max(t for _, t, _ in candidates)
        )
        if candidates
        else []
    )
    rows, stored = [], []
    for seq, t, p in candidates:
        custody = next((c for c in custodies if c.started_at <= t and (c.ended_at is None or t < c.ended_at)), None)
        if custody is None:
            rejected[seq] = "no_custody"
            continue
        rows.append(
            {
                "vehicle_id": custody.vehicle_id,
                "recorded_at": t,
                "custody_id": custody.id,
                "driver_id": device.employee_id,
                "device_id": device.device_id,
                "device_seq": seq,
                "device_offset_s": offset,
                "lat": p["lat"],
                "lng": p["lng"],
                "accuracy_m": p.get("accuracy_m"),
                "speed_kmh": p.get("speed_kmh"),
                "heading": p.get("heading"),
            }
        )
        stored.append(seq)

    months = {_month(r["recorded_at"]) for r in rows}
    for month in months:
        ensure_partition(db, month)
    if rows:  # a resent point hits the primary key and is acknowledged as stored
        db.execute(insert(Position).values(rows).on_conflict_do_nothing())
    new_rejections = [
        {"device_id": device.device_id, "device_seq": s, "reason": r} for s, r in rejected.items() if s in batch
    ]
    if new_rejections:
        db.execute(insert(RejectedPoint).values(new_rejections).on_conflict_do_nothing())
    if mocks:
        custody = fleet.open_custody_for_driver(db, device.employee_id)
        db.execute(
            insert(MockEvent)
            .values(
                [
                    {
                        "device_id": device.device_id,
                        "recorded_at": t,
                        "driver_id": device.employee_id,
                        "custody_id": custody.id if custody else None,
                    }
                    for _, t in mocks
                ]
            )
            .on_conflict_do_nothing()
        )
        notifications.raise_alert(
            db,
            "mock_location",
            company_id=custody.company_id if custody else device.company_id,
            entity_type="employee",
            entity_id=device.employee_public_id,
            params={"driver": device.name},
            dedupe_key=f"mock:{device.device_id}:{business_date(now)}",
            once=True,
        )
        # TRK-M-02: the attempt is also a violation waiting for review (once a day per phone)
        violations.fake_location(db, employee_id=device.employee_id, device_id=device.device_id, at=mocks[0][1])
    _speeding(db, device, rows, custodies)

    latest: dict[int, dict] = {}
    for r in rows:
        if r["vehicle_id"] not in latest or r["recorded_at"] > latest[r["vehicle_id"]]["recorded_at"]:
            latest[r["vehicle_id"]] = r
    updated = []
    for r in latest.values():
        values = {
            k: r[k]
            for k in ("vehicle_id", "recorded_at", "custody_id", "driver_id", "lat", "lng", "speed_kmh", "heading")
        }
        stmt = insert(LastPosition).values(**values, signal_lost_alerted_at=None)
        changed = db.execute(
            stmt.on_conflict_do_update(
                index_elements=["vehicle_id"],
                set_={**{k: stmt.excluded[k] for k in values if k != "vehicle_id"}, "signal_lost_alerted_at": None},
                where=LastPosition.recorded_at < stmt.excluded.recorded_at,
            ).returning(LastPosition.vehicle_id)
        ).first()
        if changed:
            updated.append(r)
            notifications.resolve(db, f"signal_lost:{r['custody_id']}:", prefix=True)
    db.commit()
    _partitions.update(months)
    _publish(db, updated, device)
    return {
        "stored_seqs": sorted(stored),
        "rejected": [{"seq": s, "reason": r} for s, r in sorted(rejected.items())],
        "server_time": now,
    }


def _speeding(db: Session, device: identity.DevicePrincipal, rows: list[dict], custodies: list) -> None:
    """BR-13: a point faster than the limit (with a usable accuracy) is an alert, once a custody a day; only a
    supervisor turns it into a violation."""
    limit = org.get_section(db, "tracking").speed_limit_kmh
    if not limit:
        return
    fastest: dict[tuple[int, object], dict] = {}
    for r in rows:
        if (r["speed_kmh"] or 0) > limit and (r["accuracy_m"] is None or r["accuracy_m"] <= MAX_SPEED_ACCURACY_M):
            key = (r["custody_id"], business_date(r["recorded_at"]))
            if key not in fastest or r["speed_kmh"] > fastest[key]["speed_kmh"]:
                fastest[key] = r
    if not fastest:
        return
    by_id = {c.id: c for c in custodies}
    plates = fleet.plate_numbers(db, {r["vehicle_id"] for r in fastest.values()})
    for (custody_id, day), r in fastest.items():
        c = by_id[custody_id]
        notifications.raise_alert(
            db,
            "speeding",
            company_id=c.company_id,
            entity_type="custody",
            entity_id=c.public_id,
            params={"driver": device.name, "plate": plates.get(r["vehicle_id"]), "speed": round(r["speed_kmh"])},
            dedupe_key=f"speeding:{custody_id}:{day}",
            once=True,
        )


def _publish(db: Session, rows: list[dict], device: identity.DevicePrincipal) -> None:
    if not rows:
        return
    vehicles = fleet.vehicles(db, [r["vehicle_id"] for r in rows])
    working = fleet.on_duty_now(db, {r["custody_id"] for r in rows if r.get("custody_id")})
    for r in rows:
        v = vehicles[r["vehicle_id"]]
        live.broker().publish(
            v.company_id,
            {
                "vehicle": {"id": str(v.public_id), "plate_number": v.plate_number},
                "on_duty": r.get("custody_id") in working,
                "driver": {"name": device.name},
                "lat": r["lat"],
                "lng": r["lng"],
                "speed_kmh": r["speed_kmh"],
                "heading": r["heading"],
                "recorded_at": r["recorded_at"],
            },
        )


# ------------------------------------------------------------------ live map


def company_scope(db: Session, all_companies: bool, company_ids: Iterable[int]) -> set[int]:
    if all_companies:
        return {c["id"] for c in org.list_companies(db, all_companies=True, company_ids=())}
    return set(company_ids)


def live_snapshot(
    db: Session, *, see_off_duty: bool = False, all_companies: bool, company_ids: Iterable[int]
) -> list[dict]:
    """Every vehicle in custody now, with its last position (or none yet), whether its signal is lost and whether
    its driver's day is on. Off duty, the position is shown only to who may see it (BRD FR-TRK-09)."""
    scope = company_scope(db, all_companies, company_ids)
    custodies = [c for c in fleet.open_custodies(db) if c.company_id in scope]
    if not custodies:
        return []
    vehicles = fleet.vehicles(db, [c.vehicle_id for c in custodies])
    drivers = people.names(db, [c.driver_id for c in custodies])
    positions = {
        p.vehicle_id: p
        for p in db.scalars(select(LastPosition).where(LastPosition.vehicle_id.in_([c.vehicle_id for c in custodies])))
    }
    lost_after = timedelta(minutes=org.get_section(db, "tracking").signal_loss_minutes)
    working = fleet.on_duty_now(db, [c.id for c in custodies])
    now, out = utcnow(), []
    for c in custodies:
        v, p = vehicles[c.vehicle_id], positions.get(c.vehicle_id)
        p = p if p is not None and p.custody_id == c.id else None  # a position from an earlier custody is stale
        reference = p.recorded_at if p else c.started_at
        hidden = c.id not in working and not see_off_duty
        out.append(
            {
                "vehicle": {"id": str(v.public_id), "plate_number": v.plate_number},
                "driver": drivers.get(c.driver_id),
                "custody_id": str(c.public_id),
                "company_id": c.company_id,
                "on_duty": c.id in working,
                "position_hidden": hidden and p is not None,
                "position": None
                if p is None or hidden
                else {
                    "lat": p.lat,
                    "lng": p.lng,
                    "speed_kmh": p.speed_kmh,
                    "heading": p.heading,
                    "recorded_at": p.recorded_at,
                },
                "signal_lost": now - reference > lost_after,
            }
        )
    return out


async def live_events(
    company_ids: set[int],
    *,
    see_off_duty: bool = True,
    keepalive: float = 15.0,
    max_seconds: float = 1800.0,
    max_events: int | None = None,
) -> AsyncIterator[str]:
    """Server-sent events for the given companies (the caller's scope); a position off duty only to who may see it.
    The stream ends after max_seconds: the browser reconnects, which re-checks the session and the scope."""
    deadline, sent = time.monotonic() + max_seconds, 0
    yield "retry: 3000\n\n"
    async for message in live.broker().listen(company_ids, timeout=keepalive):
        if message is None:
            yield ": keep-alive\n\n"
        elif not see_off_duty and json.loads(message).get("on_duty") is False:
            continue
        else:
            yield f"event: position\ndata: {message}\n\n"
            sent += 1
        if time.monotonic() > deadline or (max_events is not None and sent >= max_events):
            return


# ------------------------------------------------------------------ route history


def _km(a: Position, b: Position) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlng = lat2 - lat1, math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def route(
    db: Session,
    *,
    vehicle_public_id=None,
    custody_public_id=None,
    start: datetime | None = None,
    end: datetime | None = None,
    see_off_duty: bool = False,
    all_companies: bool,
    company_ids: Iterable[int],
) -> dict:
    scope = {"all_companies": all_companies, "company_ids": company_ids}
    if custody_public_id is not None:
        c = fleet.custody_ref_by_public_id(db, custody_public_id, **scope)
        vehicle_id = c.vehicle_id
        start = max(start or c.started_at, c.started_at)
        end = min(end or c.ended_at or utcnow(), c.ended_at or utcnow())
    elif vehicle_public_id is not None:
        vehicle_id = fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id
        if start is None or end is None:
            raise AppError(422, "range_required")
    else:
        raise AppError(422, "range_required")
    if end <= start:
        raise AppError(422, "invalid_range")
    if end - start > MAX_ROUTE_RANGE:
        raise AppError(422, "range_too_long", hours=int(MAX_ROUTE_RANGE.total_seconds() // 3600))
    points = list(
        db.scalars(
            select(Position)
            .where(Position.vehicle_id == vehicle_id, Position.recorded_at >= start, Position.recorded_at < end)
            .order_by(Position.recorded_at)
            .limit(MAX_ROUTE_POINTS + 1)
        )
    )
    truncated = len(points) > MAX_ROUTE_POINTS
    points = points[:MAX_ROUTE_POINTS]
    # BRD FR-TRK-09: a point is on duty within one of the driver's work days on this custody; the rest of the
    # custody (before the day started, after it ended) is his own time, shown only to who may see it
    periods = fleet.work_periods(db, vehicle_id, start, end)
    flagged = [(p, any(c == p.custody_id and a <= p.recorded_at <= b for c, a, b in periods)) for p in points]
    shown = flagged if see_off_duty else [(p, on) for p, on in flagged if on]
    v = fleet.vehicles(db, [vehicle_id])[vehicle_id]
    drivers = people.names(db, {p.driver_id for p, _ in shown})
    pairs = list(zip(shown, shown[1:], strict=False))
    return {
        "vehicle": {"id": str(v.public_id), "plate_number": v.plate_number},
        "from": start,
        "to": end,
        "distance_km": round(sum(_km(a, b) for (a, _), (b, _) in pairs), 2),
        "off_duty_km": round(sum(_km(a, b) for (a, x), (b, y) in pairs if not x and not y), 2),
        "hidden_off_duty": len(flagged) - len(shown),
        "truncated": truncated,
        "drivers": list(drivers.values()),
        "points": [
            {
                "t": p.recorded_at,
                "lat": p.lat,
                "lng": p.lng,
                "speed_kmh": p.speed_kmh,
                "heading": p.heading,
                "accuracy_m": p.accuracy_m,
                "on_duty": on,
            }
            for p, on in shown
        ],
    }


# ------------------------------------------------------------------ device health


HEALTH_CHECKS = {
    "location_permission_off": lambda s: s.get("location_permission") not in (None, "always"),
    "gps_off": lambda s: s.get("gps_enabled") is False,
    "tracking_stopped": lambda s: s.get("tracking_service_running") is False,
}


def heartbeat(db: Session, device: identity.DevicePrincipal, status: dict) -> dict:
    """The app reports its health every few minutes. During custody, location permission other than "always",
    GPS off or the tracking service stopped raise an alert, which closes itself when the report is healthy again."""
    identity.record_device_status(db, device.device_id, status)
    custody = fleet.open_custody_for_driver(db, device.employee_id)
    plate = fleet.plate_numbers(db, [custody.vehicle_id])[custody.vehicle_id] if custody else None
    for kind, failing in HEALTH_CHECKS.items():
        key = f"{kind}:{device.device_id}"
        if custody is not None and failing(status):
            notifications.raise_alert(
                db,
                kind,
                company_id=custody.company_id,
                entity_type="employee",
                entity_id=device.employee_public_id,
                params={"driver": device.name, "plate": plate},
                dedupe_key=key,
            )
        else:
            notifications.resolve(db, key)
    db.commit()
    settings = org.get_section(db, "tracking")
    return {
        "server_time": utcnow(),
        "tracking_required": custody is not None,
        "interval_moving_s": settings.interval_moving_s,
        "interval_stationary_s": settings.interval_stationary_s,
    }


# ------------------------------------------------------------------ periodic jobs


def scan_signal_loss(db: Session) -> int:
    """Every minute: a vehicle in custody whose last point is older than the configured minutes raises one alert
    per silence (acknowledging it does not bring it back; the next silence alerts again)."""
    lost_after = timedelta(minutes=org.get_section(db, "tracking").signal_loss_minutes)
    now, raised = utcnow(), 0
    custodies = fleet.open_custodies(db)
    if not custodies:
        return 0
    positions = {
        p.vehicle_id: p
        for p in db.scalars(select(LastPosition).where(LastPosition.vehicle_id.in_([c.vehicle_id for c in custodies])))
    }
    plates = fleet.plate_numbers(db, [c.vehicle_id for c in custodies])
    drivers = people.names(db, [c.driver_id for c in custodies])
    for c in custodies:
        p = positions.get(c.vehicle_id)
        p = p if p is not None and p.custody_id == c.id else None
        reference = p.recorded_at if p else c.started_at
        if now - reference <= lost_after:
            continue
        if notifications.raise_alert(
            db,
            "signal_lost",
            company_id=c.company_id,
            entity_type="custody",
            entity_id=c.public_id,
            params={
                "driver": drivers.get(c.driver_id, {}).get("name", ""),
                "plate": plates.get(c.vehicle_id),
                "minutes": int((now - reference).total_seconds() // 60),
            },
            dedupe_key=f"signal_lost:{c.id}:{reference.isoformat()}",
            once=True,
        ):
            raised += 1
            if p is not None:
                p.signal_lost_alerted_at = now
            violations.signal_lost(db, employee_id=c.driver_id, custody_id=c.id, lost_at=reference)  # TRK-M-03
    db.commit()
    return raised


def maintain_partitions(db: Session) -> int:
    """Daily: the current and the next two months always have a partition; with a retention set, the months older
    than it are deleted whole (BRD privacy and retention, a client setting). Returns how many months were deleted."""
    current = month = _month(utcnow())
    months = []
    for _ in range(3):
        _partitions.discard(month)
        ensure_partition(db, month)
        months.append(month)
        month = (month + timedelta(days=32)).replace(day=1)
    db.commit()
    _partitions.update(months)
    keep = org.get_section(db, "tracking").retention_months
    if not keep:
        return 0
    index = current.year * 12 + current.month - 1 - keep
    cutoff = date(index // 12, index % 12 + 1, 1)
    dropped = db.scalar(text("SELECT tracking.drop_partitions_before(:m)"), {"m": cutoff}) or 0
    if dropped:
        audit.record(
            db,
            action="tracking.points_deleted",
            entity_type="tracking",
            actor_type="system",
            after={"before_month": cutoff, "months": dropped, "retention_months": keep},
        )
    db.commit()
    return dropped
