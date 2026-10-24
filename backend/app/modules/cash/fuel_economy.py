"""Fuel economy: litres per 100 km and cost per km, per vehicle, per driver and per month, with the fills that could
not be counted and why.

A fill is a driver's approved fuel claim (its odometer typed in the app, its litres from the app or the accountant) or
an approved fuel expense of a vehicle (expense type "fuel": its quantity in litres, its odometer). The fuel burnt over
a distance is what was put in after the reading the distance starts from: between two fills with a trusted odometer,
the litres (and the money) of every fill after the first, up to and including the second. A stretch counts only when

- both odometers are trusted: given, going forward, and not contradicted by the vehicle's photographed readings
  around the fill's time (within READING_TOLERANCE_KM);
- the litres of every fill in it are known (one fill with no litres leaves the stretch unknown, never guessed);
- its distance is not longer than a tank lasts (MAX_GAP_KM: a fill is missing) and its consumption is plausible.

A figure (vehicle, driver, month, fleet) needs MIN_PAIRS stretches and MIN_KM kilometres; otherwise it is None and
the reasons say what is missing. A driver's figure uses the stretches between two of his own fills. Pending claims are
not counted (not reviewed), only reported. Nothing here is stored: it is computed from the records when asked.
"""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, business_date
from app.core.errors import AppError
from app.modules.cash.models import FuelClaim
from app.modules.fleet import service as fleet
from app.modules.people import service as people

LOOKBACK = timedelta(days=62)  # the fill before the period starts the period's first stretch
MIN_PAIRS = 2
MIN_KM = 300
MAX_GAP_KM = 1500
READING_TOLERANCE_KM = 20
PLAUSIBLE_L100 = (Decimal("3"), Decimal("40"))
STRETCH_OUTLIER = Decimal("0.5")  # a stretch 50% off the vehicle's own figure is an exception
ABOVE_FLEET = Decimal("25")  # a vehicle 25% above the fleet's median is an exception
PRICE_OUTLIER = Decimal("0.25")  # a price per litre 25% off the period's median
MAX_SPAN = 400  # days
CENT = Decimal("0.01")
MILLS = Decimal("0.001")


def _fills(db: Session, first: date, last: date, vehicle_id: int | None) -> tuple[list[dict], dict[int, int]]:
    """Approved claims and fuel expenses with a vehicle, from LOOKBACK before first to last, oldest first; and the
    claims of the period still pending (not counted), by vehicle."""
    from app.modules.finance import service as finance  # finance imports cash

    start = first - LOOKBACK
    lo = datetime.combine(start, time.min, KUWAIT)
    hi = datetime.combine(last + timedelta(days=1), time.min, KUWAIT)
    q = select(FuelClaim).where(FuelClaim.paid_at >= lo, FuelClaim.paid_at < hi, FuelClaim.status == "approved")
    pending = select(FuelClaim.vehicle_id, func.count()).where(
        FuelClaim.status == "pending",
        FuelClaim.paid_at >= datetime.combine(first, time.min, KUWAIT),
        FuelClaim.paid_at < hi,
    )
    if vehicle_id is not None:
        q, pending = q.where(FuelClaim.vehicle_id == vehicle_id), pending.where(FuelClaim.vehicle_id == vehicle_id)
    fills = [
        {
            "source": "claim",
            "id": str(c.public_id),
            "vehicle_id": c.vehicle_id,
            "driver_id": c.employee_id,
            "at": c.paid_at,
            "day": business_date(c.paid_at),
            "amount": c.approved_amount or c.amount,
            "litres": c.litres,
            "km": c.odometer_km,
            "dated_only": False,
        }
        for c in db.scalars(q)
    ]
    for e in finance.fuel_fills(db, None if vehicle_id is None else [vehicle_id], start, last):
        fills.append(
            {
                "source": "expense",
                "id": e["id"],
                "number": e["number"],
                "vehicle_id": e["vehicle_id"],
                "driver_id": e["employee_id"],
                "at": datetime.combine(e["day"], time(12), KUWAIT),  # a date only: midday, for the order
                "day": e["day"],
                "amount": e["amount"],
                "litres": e["litres"],
                "km": e["odometer_km"],
                "dated_only": True,
            }
        )
    fills.sort(key=lambda f: (f["vehicle_id"], f["at"], f["km"] or 0))
    return fills, dict(db.execute(pending.group_by(FuelClaim.vehicle_id)).all())


def _conflicts(f: dict, readings: list[tuple[datetime, int]]) -> bool:
    """The fill's odometer against the photographed readings just before and just after it (for an expense, which
    has a date only: before and after that day)."""
    if not readings:
        return False
    times = [r[0] for r in readings]
    if f["dated_only"]:
        lo = datetime.combine(f["day"], time.min, KUWAIT)
        before, after = bisect_left(times, lo) - 1, bisect_right(times, lo + timedelta(days=1))
    else:
        before, after = bisect_right(times, f["at"]) - 1, bisect_left(times, f["at"])
    if before >= 0 and f["km"] < readings[before][1] - READING_TOLERANCE_KM:
        return True
    return after < len(readings) and f["km"] > readings[after][1] + READING_TOLERANCE_KM


def _figure(stretches: list[dict]) -> dict:
    """The figure of a set of stretches, or None with why: too few stretches, too little distance."""
    km = sum(s["km"] for s in stretches)
    litres = sum((s["litres"] for s in stretches), Decimal(0))
    amount = sum((s["amount"] for s in stretches), Decimal(0))
    enough = len(stretches) >= MIN_PAIRS and km >= MIN_KM
    return {
        "stretches": len(stretches),
        "km": km,
        "litres": litres.quantize(CENT),
        "amount": amount.quantize(MILLS),
        "l_per_100km": (litres * 100 / km).quantize(CENT) if enough else None,
        "cost_per_km": (amount / km).quantize(MILLS) if enough else None,
        "insufficient": None if enough else ("few_stretches" if len(stretches) < MIN_PAIRS else "short_distance"),
    }


def economy(
    db: Session,
    *,
    first: date,
    last: date,
    vehicle_public_id=None,
    all_companies: bool,
    company_ids: Iterable[int],
) -> dict:
    if last < first or (last - first).days > MAX_SPAN:
        raise AppError(422, "invalid_range")
    scope = {"all_companies": all_companies, "company_ids": company_ids}
    vehicle_id = fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id if vehicle_public_id else None
    fills, pending_by_vehicle = _fills(db, first, last, vehicle_id)
    # by the vehicle's company: all of a visible car's fills (whoever's claim), so its stretches are whole
    refs = fleet.vehicles(db, {f["vehicle_id"] for f in fills} | set(pending_by_vehicle))
    visible = {v for v, ref in refs.items() if all_companies or ref.company_id in set(company_ids)}
    fills = [f for f in fills if f["vehicle_id"] in visible]
    pending = sum(n for v, n in pending_by_vehicle.items() if v in visible)
    readings = fleet.readings_between(
        db,
        {f["vehicle_id"] for f in fills},
        datetime.combine(first - LOOKBACK - timedelta(days=2), time.min, KUWAIT),
        datetime.combine(last + timedelta(days=2), time.min, KUWAIT),
    )
    period = [f for f in fills if first <= f["day"] <= last]
    prices = [f["amount"] / f["litres"] for f in period if f["litres"]]
    median_price = median(prices) if prices else None
    for f in fills:
        f["flags"] = []
        if f["km"] is None:
            f["flags"].append("no_odometer")
        elif _conflicts(f, readings.get(f["vehicle_id"], [])):
            f["flags"].append("odometer_conflict")
        if not f["litres"]:
            f["flags"].append("no_litres")
        elif median_price and abs(f["amount"] / f["litres"] - median_price) > median_price * PRICE_OUTLIER:
            f["flags"].append("price_outlier")

    # the stretches between consecutive fills with a trusted odometer
    stretches: list[dict] = []
    by_vehicle: dict[int, list[dict]] = defaultdict(list)
    for f in fills:
        by_vehicle[f["vehicle_id"]].append(f)
    for rows in by_vehicle.values():
        anchor, between = None, []
        for f in rows:
            trusted = f["km"] is not None and "odometer_conflict" not in f["flags"]
            if trusted and anchor is not None and f["km"] <= anchor["km"]:
                f["flags"].append("odometer_backwards")
                trusted = False
            between.append(f)
            if not trusted:
                continue
            if anchor is not None:
                stretch = _stretch(anchor, between)
                if stretch is not None and first <= f["day"] <= last:
                    stretches.append(stretch)
            anchor, between = f, []

    vehicle_figures = {}
    for vid in by_vehicle:
        mine = [s for s in stretches if s["vehicle_id"] == vid]
        vehicle_figures[vid] = _figure(mine)
        own = vehicle_figures[vid]["l_per_100km"]
        for s in mine:  # a stretch far off the vehicle's own figure
            if own and abs(s["l_per_100km"] - own) > own * STRETCH_OUTLIER:
                s["fill"]["flags"].append("consumption_outlier")
    known = [x["l_per_100km"] for x in vehicle_figures.values() if x["l_per_100km"] is not None]
    fleet_median = median(known) if known else None

    cards = fleet.vehicle_cards(db, by_vehicle.keys())
    names = people.names(db, {f["driver_id"] for f in fills if f["driver_id"]})
    vehicles = []
    for vid, rows in by_vehicle.items():
        mine = [f for f in rows if first <= f["day"] <= last]
        if not mine and vehicle_figures[vid]["stretches"] == 0:
            continue  # only fills from before the period
        fig = vehicle_figures[vid]
        vs = None
        if fig["l_per_100km"] is not None and fleet_median:
            vs = ((fig["l_per_100km"] - fleet_median) * 100 / fleet_median).quantize(Decimal("0.1"))
        vehicles.append(
            {
                "vehicle": cards.get(vid, {}),
                "fills": len(mine),
                "fills_litres": sum(1 for f in mine if f["litres"]),
                "fills_odometer": sum(1 for f in mine if f["km"] is not None),
                "litres": sum((f["litres"] or Decimal(0) for f in mine), Decimal(0)).quantize(CENT),
                "spent": sum((f["amount"] for f in mine), Decimal(0)).quantize(MILLS),
                "vs_fleet_pct": vs,
                "above_fleet": vs is not None and vs > ABOVE_FLEET,
                "skipped": dict(Counter(flag for f in mine for flag in f["flags"])),
            }
            | fig
        )
    vehicles.sort(key=lambda x: (x["l_per_100km"] is None, -(x["l_per_100km"] or 0)))

    drivers = []
    by_driver: dict[int, list[dict]] = defaultdict(list)
    for s in stretches:
        if s["driver_id"] is not None:
            by_driver[s["driver_id"]].append(s)
    for driver_id in {f["driver_id"] for f in period if f["driver_id"]} | set(by_driver):
        drivers.append(
            {"driver": names.get(driver_id), "fills": sum(1 for f in period if f["driver_id"] == driver_id)}
            | _figure(by_driver.get(driver_id, []))
        )
    drivers.sort(key=lambda x: (x["l_per_100km"] is None, -(x["l_per_100km"] or 0)))

    months = []
    month_keys = sorted({f["day"].replace(day=1) for f in period} | {s["month"] for s in stretches})
    for m in month_keys:
        in_month = [f for f in period if f["day"].replace(day=1) == m]
        months.append(
            {
                "month": m,
                "fills": len(in_month),
                "litres": sum((f["litres"] or Decimal(0) for f in in_month), Decimal(0)).quantize(CENT),
                "spent": sum((f["amount"] for f in in_month), Decimal(0)).quantize(MILLS),
            }
            | _figure([s for s in stretches if s["month"] == m])
        )

    exceptions = [
        {
            "source": f["source"],
            "id": f["id"],
            "number": f.get("number"),
            "vehicle": cards.get(f["vehicle_id"], {}),
            "driver": names.get(f["driver_id"]),
            "at": f["at"],
            "day": f["day"],
            "dated_only": f["dated_only"],
            "amount": f["amount"],
            "litres": f["litres"],
            "km": f["km"],
            "flags": f["flags"],
        }
        for f in period
        if f["flags"]
    ]
    exceptions.sort(key=lambda x: x["at"], reverse=True)
    for v in vehicles:
        if v["above_fleet"]:
            exceptions.insert(0, {"source": "vehicle", "vehicle": v["vehicle"], "flags": ["above_fleet"],
                                  "vs_fleet_pct": v["vs_fleet_pct"], "l_per_100km": v["l_per_100km"]})  # fmt: skip
    return {
        "first": first,
        "last": last,
        "fleet": _figure(stretches)
        | {
            "median_l_per_100km": fleet_median.quantize(CENT) if fleet_median is not None else None,
            "median_price_per_litre": median_price.quantize(MILLS) if median_price is not None else None,
            "fills": len(period),
            "fills_litres": sum(1 for f in period if f["litres"]),
            "fills_odometer": sum(1 for f in period if f["km"] is not None),
            "spent": sum((f["amount"] for f in period), Decimal(0)).quantize(MILLS),
            "litres_total": sum((f["litres"] or Decimal(0) for f in period), Decimal(0)).quantize(CENT),
            "pending_claims": pending,
        },
        "vehicles": vehicles,
        "drivers": drivers,
        "months": months,
        "exceptions": exceptions[:300],
        "rules": {
            "min_stretches": MIN_PAIRS,
            "min_km": MIN_KM,
            "max_gap_km": MAX_GAP_KM,
            "reading_tolerance_km": READING_TOLERANCE_KM,
            "plausible_l_per_100km": [PLAUSIBLE_L100[0], PLAUSIBLE_L100[1]],
            "above_fleet_pct": ABOVE_FLEET,
        },
    }


def _stretch(anchor: dict, between: list[dict]) -> dict | None:
    """From the anchor's reading to the last fill of `between` (trusted), with the fuel put in after the anchor; None
    (and the reason on the closing fill) when it cannot count."""
    end = between[-1]
    km = end["km"] - anchor["km"]
    if any(not f["litres"] for f in between):
        end["flags"].append("stretch_litres_missing")
        return None
    if km > MAX_GAP_KM:
        end["flags"].append("gap_too_long")
        return None
    litres = sum((f["litres"] for f in between), Decimal(0))
    l100 = litres * 100 / km
    if not PLAUSIBLE_L100[0] <= l100 <= PLAUSIBLE_L100[1]:
        end["flags"].append("implausible")
        return None
    drivers = {anchor["driver_id"], *(f["driver_id"] for f in between)}
    return {
        "vehicle_id": end["vehicle_id"],
        "driver_id": anchor["driver_id"] if len(drivers) == 1 else None,  # his own stretch only
        "km": km,
        "litres": litres,
        "amount": sum((f["amount"] for f in between), Decimal(0)),
        "l_per_100km": l100,
        "month": end["day"].replace(day=1),
        "fill": end,
    }
