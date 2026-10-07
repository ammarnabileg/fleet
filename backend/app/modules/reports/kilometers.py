"""Kilometers (BRD FR-RPT-03): by vehicle and by driver, the kilometers off duty, the readings waiting for review, and
the odometer against the GPS.

Each pair of consecutive odometer readings of a vehicle is a stretch; a stretch is counted in the period of its second
reading. A stretch is:
- at the center: from the center's reception (maintenance_in) to the next reading (its test drives);
- with nobody: the two readings belong to different custodies or to none (from a return to the next handover, from
  the center back to the office). Nobody is accountable for it, so it is kept apart;
- off duty: within one custody, from the end of a day to the next start of day, as the odometer alert counts it;
- on duty: any other stretch within one custody.
A reading waiting for review is not counted until it is reviewed (its corrected value then counts): a typo in it would
count thousands of kilometers twice over. A reading lower than the one before counts 0.

The GPS kilometers add up the straight lines between the phone's consecutive points of one custody: they cover what
the odometer counts with a driver (on duty and off duty), and read short where the signal was lost.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, BIGINT
from sqlalchemy.orm import Session

from app.modules.reports.filters import Filters
from app.modules.reports.service import MAX_RANGE_DAYS, _people, _period, _range, _vehicle_cards

PENDING_LIMIT = 200
KINDS = ("on_duty", "off_duty", "unattended", "center")

SCOPED = text("""
    SELECT v.id FROM fleet.vehicles v
    WHERE (:all_companies OR v.company_id = ANY(:company_ids))
      AND (CAST(:vehicle_id AS bigint) IS NULL OR v.id = :vehicle_id)
      AND (CAST(:branch_id AS bigint) IS NULL OR v.branch_id = :branch_id)
""").bindparams(bindparam("company_ids", type_=ARRAY(BIGINT)))

STRETCHES = text("""
WITH scoped AS (
    SELECT v.id FROM fleet.vehicles v
    WHERE (:all_companies OR v.company_id = ANY(:company_ids))
      AND (CAST(:vehicle_id AS bigint) IS NULL OR v.id = :vehicle_id)
      AND (CAST(:branch_id AS bigint) IS NULL OR v.branch_id = :branch_id)
),
readings AS (
    SELECT r.id, r.vehicle_id, r.custody_id, r.driver_id, r.kind, r.recorded_at,
           COALESCE(r.corrected_km, r.value_km) AS km
    FROM fleet.odometer_readings r JOIN scoped s ON s.id = r.vehicle_id
    WHERE r.review_status <> 'pending' AND r.recorded_at >= :start AND r.recorded_at < :end
    UNION ALL
    SELECT b.* FROM scoped s CROSS JOIN LATERAL (
        SELECT r.id, r.vehicle_id, r.custody_id, r.driver_id, r.kind, r.recorded_at,
               COALESCE(r.corrected_km, r.value_km) AS km
        FROM fleet.odometer_readings r
        WHERE r.vehicle_id = s.id AND r.review_status <> 'pending' AND r.recorded_at < :start
        ORDER BY r.recorded_at DESC, r.id DESC
        LIMIT 1
    ) b
),
pairs AS (
    SELECT r.*, lag(r.km) OVER w AS prev_km, lag(r.kind) OVER w AS prev_kind, lag(r.custody_id) OVER w AS prev_custody
    FROM readings r
    WINDOW w AS (PARTITION BY r.vehicle_id ORDER BY r.recorded_at, r.id)
)
SELECT vehicle_id, driver_id, custody_id, prev_custody, kind, prev_kind, GREATEST(km - prev_km, 0) AS km
FROM pairs
WHERE prev_km IS NOT NULL AND recorded_at >= :start
""").bindparams(bindparam("company_ids", type_=ARRAY(BIGINT)))

GPS = text("""
SELECT vehicle_id, driver_id, sum(d) AS km FROM (
    SELECT p.vehicle_id, p.driver_id,
           2 * 6371.0088 * asin(LEAST(1, sqrt(
               power(sin(radians(p.lat - p.plat) / 2), 2)
               + cos(radians(p.plat)) * cos(radians(p.lat)) * power(sin(radians(p.lng - p.plng) / 2), 2)
           ))) AS d
    FROM (
        SELECT vehicle_id, driver_id, lat, lng, lag(lat) OVER w AS plat, lag(lng) OVER w AS plng
        FROM tracking.positions
        WHERE recorded_at >= :start AND recorded_at < :end AND vehicle_id = ANY(:vehicle_ids)
          AND (CAST(:driver_id AS bigint) IS NULL OR driver_id = :driver_id)
        WINDOW w AS (PARTITION BY vehicle_id, custody_id ORDER BY recorded_at)
    ) p
    WHERE p.plat IS NOT NULL
) x
GROUP BY vehicle_id, driver_id
""").bindparams(bindparam("vehicle_ids", type_=ARRAY(BIGINT)))

DAYS = text("""
SELECT r.driver_id, count(DISTINCT r.business_date) AS days
FROM fleet.odometer_readings r
WHERE r.kind = 'start_day' AND r.recorded_at >= :start AND r.recorded_at < :end AND r.vehicle_id = ANY(:vehicle_ids)
GROUP BY r.driver_id
""").bindparams(bindparam("vehicle_ids", type_=ARRAY(BIGINT)))

PENDING = text("""
WITH scoped AS (
    SELECT v.id FROM fleet.vehicles v
    WHERE (:all_companies OR v.company_id = ANY(:company_ids))
      AND (CAST(:vehicle_id AS bigint) IS NULL OR v.id = :vehicle_id)
      AND (CAST(:branch_id AS bigint) IS NULL OR v.branch_id = :branch_id)
)
SELECT r.public_id, r.vehicle_id, r.driver_id, r.kind, r.value_km, r.flags, r.recorded_at, count(*) OVER () AS total
FROM fleet.odometer_readings r JOIN scoped s ON s.id = r.vehicle_id
WHERE r.review_status = 'pending' AND r.recorded_at >= :start AND r.recorded_at < :end
  AND (CAST(:driver_id AS bigint) IS NULL OR r.driver_id = :driver_id)
ORDER BY r.recorded_at DESC
LIMIT :limit
""").bindparams(bindparam("company_ids", type_=ARRAY(BIGINT)))


def stretch_kind(prev_kind: str, kind: str, prev_custody: int | None, custody: int | None) -> str:
    if prev_kind == "maintenance_in":
        return "center"
    if prev_custody is None or prev_custody != custody:
        return "unattended"
    if prev_kind in ("return", "end_day") and kind in ("handover", "start_day"):
        return "off_duty"
    return "on_duty"


def _km(value: float) -> Decimal:
    return Decimal(str(round(value, 1)))


def kilometers_report(
    db: Session, *, date_from: date, date_to: date, filters: Filters, all_companies: bool, company_ids
) -> dict:
    _range(date_from, date_to)
    start, end = _period(date_from, date_to)
    company_ids = list(company_ids)
    scope = {
        "all_companies": all_companies,
        "company_ids": company_ids,
        "vehicle_id": filters.vehicle_id,
        "branch_id": filters.branch_id,
        "start": start,
        "end": end,
    }
    vehicles: dict[int, dict] = defaultdict(lambda: dict.fromkeys(KINDS, 0))
    drivers: dict[int, dict] = defaultdict(lambda: dict.fromkeys(("on_duty", "off_duty"), 0))
    for r in db.execute(STRETCHES, scope).mappings():
        kind = stretch_kind(r["prev_kind"], r["kind"], r["prev_custody"], r["custody_id"])
        driver = r["driver_id"] if kind in ("on_duty", "off_duty") else None
        if filters.driver_id is not None and driver != filters.driver_id:
            continue
        vehicles[r["vehicle_id"]][kind] += r["km"]
        if driver is not None:
            drivers[driver][kind] += r["km"]

    vehicle_ids = [v for (v,) in db.execute(SCOPED, scope)]
    gps_by_vehicle: dict[int, float] = defaultdict(float)
    gps_by_driver: dict[int, float] = defaultdict(float)
    days: dict[int, int] = {}
    if vehicle_ids:
        gps_params = {"start": start, "end": end, "vehicle_ids": vehicle_ids, "driver_id": filters.driver_id}
        for r in db.execute(GPS, gps_params).mappings():
            gps_by_vehicle[r["vehicle_id"]] += r["km"]
            gps_by_driver[r["driver_id"]] += r["km"]
        days = {r.driver_id: r.days for r in db.execute(DAYS, gps_params) if r.driver_id is not None}
        for v in gps_by_vehicle:
            vehicles[v]  # a vehicle with GPS points and no odometer stretch still shows
        for d in gps_by_driver:
            if filters.driver_id is None or d == filters.driver_id:
                drivers[d]

    cards = _vehicle_cards(db, vehicles)
    by_vehicle = []
    for vid, k in vehicles.items():
        with_driver = k["on_duty"] + k["off_duty"]
        gps = _km(gps_by_vehicle.get(vid, 0.0))
        by_vehicle.append(
            {
                "vehicle": cards.get(vid),
                "km": sum(k.values()),
                **k,
                "with_driver": with_driver,
                "gps": gps,
                "difference": Decimal(with_driver) - gps,
                "difference_percent": round((Decimal(with_driver) - gps) * 100 / with_driver, 1)
                if with_driver
                else None,
            }
        )
    by_vehicle.sort(key=lambda r: (-r["km"], r["vehicle"]["plate_number"] if r["vehicle"] else ""))

    names = _people(db, drivers)
    by_driver = []
    for did, k in drivers.items():
        n = days.get(did, 0)
        by_driver.append(
            {
                "driver": names.get(did),
                "days": n,
                "on_duty": k["on_duty"],
                "off_duty": k["off_duty"],
                "gps": _km(gps_by_driver.get(did, 0.0)),
                "km_per_day": round(Decimal(k["on_duty"] + k["off_duty"]) / n, 1) if n else None,
            }
        )
    by_driver.sort(key=lambda r: (-(r["on_duty"] + r["off_duty"]), r["driver"]["id"] if r["driver"] else ""))

    rows = list(db.execute(PENDING, scope | {"driver_id": filters.driver_id, "limit": PENDING_LIMIT}).mappings())
    pending_cards = _vehicle_cards(db, {r["vehicle_id"] for r in rows})
    pending_names = _people(db, {r["driver_id"] for r in rows})
    pending = [
        {
            "id": str(r["public_id"]),
            "vehicle": pending_cards.get(r["vehicle_id"]),
            "driver": pending_names.get(r["driver_id"]),
            "kind": r["kind"],
            "value_km": r["value_km"],
            "flags": list(r["flags"]),
            "recorded_at": r["recorded_at"],
        }
        for r in rows
    ]
    totals = {k: sum(r[k] for r in by_vehicle) for k in ("km", *KINDS, "with_driver")}
    totals["gps"] = sum((r["gps"] for r in by_vehicle), Decimal("0.0"))
    return {
        "from": date_from,
        "to": date_to,
        "max_days": MAX_RANGE_DAYS,
        "totals": totals,
        "by_vehicle": by_vehicle,
        "by_driver": by_driver,
        "pending": pending,
        "pending_count": rows[0]["total"] if rows else 0,
    }
