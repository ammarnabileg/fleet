"""Fuel (BRD FR-FUL-01..05, BR-07, BR-08, UAT-03).

A fill is sent from the driver's app (camera photos of the invoice and the odometer, from his phone) or entered by
the office. Before it is approved it is checked (FR-FUL-02):
- the litres within the tank of its make and model;
- the amount at the official price of that day for that fuel, within the tolerance (1% by default, BR-08);
- a fuel its model takes;
- the odometer at or above the vehicle's last reading and its last fill, and no further than the daily distance
  limit allows for the days since.
A fill that passes every check is approved at once and recorded in finance as a fuel expense. A fill that fails any,
or cannot be checked (no reference for its model, no official price), waits for the accountant, who approves it only
with the reason (FR-FUL-03) or refuses it with the reason; the driver is told of a refusal.

The consumption (FR-FUL-04) of an approved fill is its litres over the kilometers since the vehicle's previous
approved fill (each fill taken as filling the tank), against the reference of its model: over by the alert share
(20% by default, BR-07) raises an alert. The period's figures per vehicle are in the consumption report.
"""

import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import business_date, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.finance import service as finance
from app.modules.fleet import service as fleet
from app.modules.fuel.models import FUEL_TYPES, Fill, ModelSpec, Price
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

FILS = Decimal("0.001")
CLOCK_SKEW = timedelta(minutes=5)
APP_DELAY = timedelta(days=3)  # a fill the phone could not send at once (offline) arrives later, not much later
OFFICE_OLDEST = timedelta(days=90)
FLAGS = (
    "over_tank",
    "price_mismatch",
    "wrong_fuel_type",
    "odometer_backwards",
    "odometer_jump",
    "no_model",
    "no_price",
)
ERRORS = {"fills_invoice_sha256_idx": "fuel_fill_exists", "prices_fuel_type_effective_from_key": "fuel_price_exists"}


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Fill.company_id.in_(list(company_ids)))


def _get(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Fill:
    q = _scoped(select(Fill).where(Fill.public_id == public_id), all_companies, company_ids)
    f = db.scalar(q.with_for_update() if lock else q)
    if f is None:
        raise AppError(404, "fuel_fill_not_found")
    return f


def _flush(db: Session, obj) -> None:
    db.add(obj)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        code = ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None


# ------------------------------------------------------------------ references: prices and models


def price_on(db: Session, fuel_type: str, day: date) -> Decimal | None:
    return db.scalar(
        select(Price.price)
        .where(Price.fuel_type == fuel_type, Price.effective_from <= day)
        .order_by(Price.effective_from.desc())
        .limit(1)
    )


def list_prices(db: Session) -> dict:
    rows = list(db.scalars(select(Price).order_by(Price.fuel_type, Price.effective_from.desc())))
    users = identity.user_names(db, {p.created_by for p in rows})
    today = business_date(utcnow())
    return {
        "current": {t: price_on(db, t, today) for t in FUEL_TYPES},
        "history": [
            {
                "fuel_type": p.fuel_type,
                "price": p.price,
                "effective_from": p.effective_from,
                "created_by": users.get(p.created_by),
                "created_at": p.created_at,
            }
            for p in rows
        ],
    }


def add_price(db: Session, data: dict, *, actor_user_id: int) -> dict:
    """An official price from a date (FR-FUL-05). It never replaces a price already set for that date: a mistake is
    corrected by a new price from the same day forward."""
    p = Price(
        fuel_type=data["fuel_type"],
        price=data["price"],
        effective_from=data["effective_from"],
        created_by=actor_user_id,
    )
    _flush(db, p)
    audit.record(
        db,
        action="fuel.price_set",
        entity_type="fuel_price",
        entity_id=p.id,
        actor_user_id=actor_user_id,
        after={"fuel_type": p.fuel_type, "price": p.price, "effective_from": p.effective_from},
    )
    db.commit()
    return list_prices(db)


def _model_out(m: ModelSpec) -> dict:
    return {
        "id": m.id,
        "make": m.make,
        "model": m.model,
        "tank_litres": m.tank_litres,
        "fuel_types": list(m.fuel_types),
        "litres_per_100km": m.litres_per_100km,
        "version": m.version,
    }


def list_models(db: Session) -> list[dict]:
    return [_model_out(m) for m in db.scalars(select(ModelSpec).order_by(ModelSpec.make, ModelSpec.model))]


def spec_for(db: Session, make: str | None, model: str | None) -> ModelSpec | None:
    if not make or not model:
        return None
    return db.scalar(
        select(ModelSpec).where(
            func.lower(ModelSpec.make) == make.strip().lower(), func.lower(ModelSpec.model) == model.strip().lower()
        )
    )


def save_model(db: Session, data: dict, *, model_id: int | None, version: int | None, actor_user_id: int) -> dict:
    """A make and model's tank, fuels and reference consumption: added, or changed at the version read."""
    if model_id is None:
        m = ModelSpec(updated_by=actor_user_id)
        before = None
    else:
        m = db.scalar(select(ModelSpec).where(ModelSpec.id == model_id).with_for_update())
        if m is None:
            raise AppError(404, "fuel_model_not_found")
        if m.version != version:
            raise AppError(409, "version_conflict")
        before = _model_out(m)
        m.version += 1
    m.make, m.model = data["make"].strip(), data["model"].strip()
    m.tank_litres, m.litres_per_100km = data["tank_litres"], data["litres_per_100km"]
    m.fuel_types = sorted(set(data["fuel_types"]))
    m.updated_by, m.updated_at = actor_user_id, utcnow()
    db.add(m)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "models_make_model_idx":
            raise
        raise AppError(409, "fuel_model_exists") from None
    audit.record(
        db,
        action="fuel.model_saved",
        entity_type="fuel_model",
        entity_id=m.id,
        actor_user_id=actor_user_id,
        before=before,
        after=_model_out(m),
    )
    db.commit()
    return _model_out(m)


# ------------------------------------------------------------------ the checks (FR-FUL-02)


def _previous_fill(db: Session, vehicle_id: int, before: datetime, exclude: int | None = None) -> Fill | None:
    q = select(Fill).where(Fill.vehicle_id == vehicle_id, Fill.status == "approved", Fill.filled_at < before)
    if exclude is not None:
        q = q.where(Fill.id != exclude)
    return db.scalar(q.order_by(Fill.filled_at.desc(), Fill.id.desc()).limit(1))


def check(db: Session, *, vehicle_id: int, litres, amount, fuel_type: str, odometer_km: int, filled_at: datetime):
    """What a fill fails, with the official price and the amount expected at it."""
    card = fleet.vehicle_cards(db, [vehicle_id])[vehicle_id]
    settings = org.get_section(db, "fuel")
    flags: list[str] = []
    spec = spec_for(db, card["make"], card["model"])
    if spec is None:
        flags.append("no_model")
    else:
        if Decimal(litres) > spec.tank_litres:
            flags.append("over_tank")
        if fuel_type not in spec.fuel_types:
            flags.append("wrong_fuel_type")
    price = price_on(db, fuel_type, business_date(filled_at))
    expected = None
    if price is None:
        flags.append("no_price")
    else:
        expected = (Decimal(litres) * price).quantize(FILS, ROUND_HALF_UP)
        if abs(Decimal(amount) - expected) > expected * settings.price_tolerance_percent / 100:
            flags.append("price_mismatch")
    known = []  # the odometer the vehicle had before this fill: its last reading, its last approved fill
    if (last := fleet.last_reading(db, vehicle_id, filled_at)) is not None:
        known.append(last)
    if (prev := _previous_fill(db, vehicle_id, filled_at)) is not None:
        known.append((prev.odometer_km, prev.filled_at))
    if known:
        km, at = max(known)
        if odometer_km < km:
            flags.append("odometer_backwards")
        else:
            days = max(1, math.ceil((filled_at - at).total_seconds() / 86400))
            if odometer_km - km > org.get_section(db, "odometer").daily_km_alert * days:
                flags.append("odometer_jump")
    return [f for f in FLAGS if f in flags], price, expected


# ------------------------------------------------------------------ recording and deciding


def _out(db: Session, rows: list[Fill]) -> list[dict]:
    cards = fleet.vehicle_cards(db, {f.vehicle_id for f in rows})
    names = people.names(db, {f.driver_id for f in rows if f.driver_id})
    users = identity.user_names(db, {u for f in rows for u in (f.decided_by, f.created_by_user) if u})
    return [
        {
            "id": str(f.public_id),
            "number": f.number,
            "vehicle": cards.get(f.vehicle_id, {}),
            "company_id": f.company_id,
            "driver": names.get(f.driver_id),
            "filled_at": f.filled_at,
            "business_date": f.business_date,
            "litres": f.litres,
            "amount": f.amount,
            "fuel_type": f.fuel_type,
            "station": f.station,
            "odometer_km": f.odometer_km,
            "invoice_sha256": f.invoice_sha256,
            "odometer_sha256": f.odometer_sha256,
            "source": f.source,
            "price": f.price,
            "expected_amount": f.expected_amount,
            "flags": list(f.flags),
            "km_since": f.km_since,
            "litres_per_100km": f.litres_per_100km,
            "status": f.status,
            "decided_by": users.get(f.decided_by),
            "decided_at": f.decided_at,
            "decision_note": f.decision_note,
            "created_by": users.get(f.created_by_user),
            "created_at": f.created_at,
        }
        for f in rows
    ]


def _audit(db: Session, action: str, f: Fill, *, actor_user_id: int | None, comment=None, after=None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="fuel_fill",
        entity_id=f.public_id,
        actor_user_id=actor_user_id,
        actor_type=None if actor_user_id else "system",
        company_id=f.company_id,
        comment=comment,
        after={"number": f.number, "status": f.status, "litres": f.litres, "amount": f.amount} | (after or {}),
    )


def _plate(db: Session, f: Fill) -> str:
    return fleet.plate_numbers(db, [f.vehicle_id]).get(f.vehicle_id, "")


def _approve(db: Session, f: Fill, *, actor_user_id: int | None, note: str | None) -> None:
    prev = _previous_fill(db, f.vehicle_id, f.filled_at, exclude=f.id)
    if prev is not None and f.odometer_km > prev.odometer_km:
        f.km_since = f.odometer_km - prev.odometer_km
        f.litres_per_100km = (f.litres * 100 / f.km_since).quantize(Decimal("0.01"), ROUND_HALF_UP)
        card = fleet.vehicle_cards(db, [f.vehicle_id])[f.vehicle_id]
        spec = spec_for(db, card["make"], card["model"])
        over = org.get_section(db, "fuel").consumption_alert_percent
        if spec is not None and f.litres_per_100km > spec.litres_per_100km * (100 + over) / 100:
            notifications.raise_alert(
                db,
                "fuel_consumption_high",
                company_id=f.company_id,
                entity_type="fuel_fill",
                entity_id=f.public_id,
                params={
                    "plate": card["plate_number"],
                    "number": f.number,
                    "consumption": f"{f.litres_per_100km}",
                    "reference": f"{spec.litres_per_100km}",
                },
                dedupe_key=f"fuel_consumption_high:{f.id}",
            )
    f.status, f.decided_by, f.decided_at, f.decision_note = "approved", actor_user_id, utcnow(), note
    f.expense_id = finance.record_fuel(
        db,
        company_id=f.company_id,
        vehicle_id=f.vehicle_id,
        employee_id=f.driver_id,
        amount=f.amount,
        litres=f.litres,
        expense_date=f.business_date,
        station=f.station,
        reference=f"FUEL-{f.number}",
        invoice_sha256=f.invoice_sha256,
        payment_method=org.get_section(db, "fuel").expense_payment,
        actor_user_id=actor_user_id,
    )
    notifications.resolve(db, f"fuel_review:{f.id}")
    _audit(db, "fuel.approved", f, actor_user_id=actor_user_id, comment=note, after={"flags": list(f.flags)})


def _record(
    db: Session,
    *,
    vehicle_id: int,
    company_id: int,
    custody: fleet.CustodyRef | None,
    data: dict,
    source: str,
    user_id: int | None = None,
    device_id: int | None = None,
) -> Fill:
    at: datetime = data["filled_at"]
    flags, price, expected = check(
        db,
        vehicle_id=vehicle_id,
        litres=data["litres"],
        amount=data["amount"],
        fuel_type=data["fuel_type"],
        odometer_km=data["odometer_km"],
        filled_at=at,
    )
    f = Fill(
        company_id=company_id,
        vehicle_id=vehicle_id,
        custody_id=custody.id if custody else None,
        driver_id=custody.driver_id if custody else None,
        filled_at=at,
        business_date=business_date(at),
        litres=data["litres"],
        amount=data["amount"],
        fuel_type=data["fuel_type"],
        station=data.get("station"),
        odometer_km=data["odometer_km"],
        invoice_sha256=data["invoice_sha256"],
        odometer_sha256=data.get("odometer_sha256"),
        source=source,
        price=price,
        expected_amount=expected,
        flags=flags,
        created_by_user=user_id,
        created_by_device=device_id,
    )
    _flush(db, f)
    db.refresh(f)
    _audit(db, "fuel.recorded", f, actor_user_id=user_id, after={"flags": flags, "source": source})
    if flags:  # stops for the accountant (UAT-03): never approved by itself
        notifications.raise_alert(
            db,
            "fuel_review",
            company_id=company_id,
            entity_type="fuel_fill",
            entity_id=f.public_id,
            params={"plate": _plate(db, f), "number": f.number, "checks": ", ".join(flags)},
            dedupe_key=f"fuel_review:{f.id}",
        )
    else:
        _approve(db, f, actor_user_id=None, note=None)
    return f


def _check_photo(db: Session, sha: str, *, device_id: int | None) -> None:
    info = files.get(db, sha)
    if info.content_type not in files.IMAGES:
        raise AppError(422, "photo_must_be_image")
    if device_id is not None and (info.uploaded_by_device != device_id or info.source != "camera"):
        raise AppError(422, "photo_not_from_camera")


def driver_record(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    """A fill from the driver's app (FR-FUL-01): in his custody at that time, with the camera photos of the invoice
    and the odometer taken on this phone."""
    at: datetime = data["filled_at"]
    now = utcnow()
    if not (now - APP_DELAY <= at <= now + CLOCK_SKEW):
        raise AppError(422, "invalid_recorded_at")
    [custody] = fleet.custodies_for_driver(db, employee_id, at, at)[-1:] or [None]
    if custody is None:
        raise AppError(409, "no_open_custody")
    if not data.get("odometer_sha256"):
        raise AppError(422, "odometer_photo_required")
    for sha in (data["invoice_sha256"], data["odometer_sha256"]):
        _check_photo(db, sha, device_id=device_id)
    f = _record(
        db,
        vehicle_id=custody.vehicle_id,
        company_id=custody.company_id,
        custody=custody,
        data=data,
        source="app",
        device_id=device_id,
    )
    db.commit()
    return _out(db, [f])[0]


def office_record(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    """A fill entered by the office (from a paper invoice): whoever held the vehicle then is its driver."""
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope)
    at: datetime = data["filled_at"]
    now = utcnow()
    if at > now + CLOCK_SKEW:
        raise AppError(422, "time_in_future")
    if at < now - OFFICE_OLDEST:
        raise AppError(422, "time_too_old")
    _check_photo(db, data["invoice_sha256"], device_id=None)
    if data.get("odometer_sha256"):
        _check_photo(db, data["odometer_sha256"], device_id=None)
    custody = fleet.custody_ref_at(db, vehicle.id, at)
    f = _record(
        db,
        vehicle_id=vehicle.id,
        company_id=vehicle.company_id,
        custody=custody,
        data=data,
        source="office",
        user_id=actor_user_id,
    )
    db.commit()
    return _out(db, [f])[0]


def decide(db: Session, public_id, *, approve: bool, note: str | None, actor_user_id: int, **scope) -> dict:
    """The accountant's decision on a fill that waits: approved only with the reason when it failed a check (FR-FUL-03),
    refused always with it."""
    f = _get(db, public_id, lock=True, **scope)
    if f.status != "pending":
        raise AppError(409, "fuel_fill_decided", status=f.status)
    note = (note or "").strip() or None
    if note is None:
        raise AppError(422, "reason_required")
    if approve:
        _approve(db, f, actor_user_id=actor_user_id, note=note)
    else:
        f.status, f.decided_by, f.decided_at, f.decision_note = "rejected", actor_user_id, utcnow(), note
        notifications.resolve(db, f"fuel_review:{f.id}")
        _audit(db, "fuel.rejected", f, actor_user_id=actor_user_id, comment=note)
        if f.driver_id is not None:
            notifications.notify_driver(
                db,
                f.driver_id,
                "fuel_rejected",
                params={"number": f.number, "reason": note},
                entity_type="fuel_fill",
                entity_id=f.public_id,
            )
    db.commit()
    return _out(db, [f])[0]


def list_fills(
    db: Session,
    *,
    status: str | None = None,
    flagged: bool | None = None,
    vehicle_public_id=None,
    driver_public_id=None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Fill), **scope)
    if status:
        q = q.where(Fill.status.in_(status.split(",")))
    if flagged is not None:
        q = q.where(func.cardinality(Fill.flags) > 0 if flagged else func.cardinality(Fill.flags) == 0)
    if vehicle_public_id:
        q = q.where(Fill.vehicle_id == fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id)
    if driver_public_id:
        q = q.where(Fill.driver_id == people.ref_by_public_id(db, driver_public_id, **scope).id)
    if date_from:
        q = q.where(Fill.business_date >= date_from)
    if date_to:
        q = q.where(Fill.business_date <= date_to)
    rows = db.scalars(q.order_by(Fill.filled_at.desc(), Fill.id.desc()).limit(min(limit, 500)).offset(offset))
    return _out(db, list(rows))


def get(db: Session, public_id, **scope) -> dict:
    return _out(db, [_get(db, public_id, **scope)])[0]


def fill_file(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    f = _get(db, public_id, **scope)
    if sha256 not in (f.invoice_sha256, f.odometer_sha256):
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def driver_form(db: Session, employee_id: int) -> dict:
    """What the app's fuel screen needs: his vehicle now, the fuels it takes, its tank and last odometer, his fills."""
    custody = fleet.open_custody_for_driver(db, employee_id)
    vehicle = None
    if custody is not None:
        card = fleet.vehicle_cards(db, [custody.vehicle_id])[custody.vehicle_id]
        spec = spec_for(db, card["make"], card["model"])
        last = fleet.last_reading(db, custody.vehicle_id, utcnow())
        vehicle = {
            "plate_number": card["plate_number"],
            "fuel_types": list(spec.fuel_types) if spec else list(FUEL_TYPES),
            "tank_litres": spec.tank_litres if spec else None,
            "last_km": last[0] if last else None,
        }
    rows = db.scalars(
        select(Fill).where(Fill.driver_id == employee_id).order_by(Fill.filled_at.desc(), Fill.id.desc()).limit(20)
    )
    mine = [
        {k: v for k, v in x.items() if k in ("id", "number", "filled_at", "litres", "amount", "fuel_type", "status")}
        | {"reason": x["decision_note"] if x["status"] == "rejected" else None}
        for x in _out(db, list(rows))
    ]
    return {"vehicle": vehicle, "fills": mine}


# ------------------------------------------------------------------ consumption (FR-FUL-04)


def consumption(db: Session, *, date_from: date, date_to: date, company_id: int | None = None, **scope) -> list[dict]:
    """Per vehicle over the period, from its approved fills: the litres after the first fill over the kilometers
    from the first fill to the last (every fill taken as filling the tank), against its model's reference."""
    q = _scoped(select(Fill).where(Fill.status == "approved"), **scope).where(
        Fill.business_date >= date_from, Fill.business_date <= date_to
    )
    if company_id is not None:
        q = q.where(Fill.company_id == company_id)
    by_vehicle: dict[int, list[Fill]] = {}
    for f in db.scalars(q.order_by(Fill.vehicle_id, Fill.filled_at, Fill.id)):
        by_vehicle.setdefault(f.vehicle_id, []).append(f)
    cards = fleet.vehicle_cards(db, by_vehicle)
    over = org.get_section(db, "fuel").consumption_alert_percent
    out = []
    for vid, fills in by_vehicle.items():
        card = cards[vid]
        spec = spec_for(db, card["make"], card["model"])
        km = fills[-1].odometer_km - fills[0].odometer_km if len(fills) > 1 else 0
        burnt = sum((f.litres for f in fills[1:]), Decimal(0))
        rate = (burnt * 100 / km).quantize(Decimal("0.01"), ROUND_HALF_UP) if km > 0 else None
        ref = spec.litres_per_100km if spec else None
        out.append(
            {
                "vehicle": card,
                "fills": len(fills),
                "litres": sum((f.litres for f in fills), Decimal(0)),
                "amount": sum((f.amount for f in fills), Decimal(0)),
                "km": km,
                "litres_per_100km": rate,
                "reference": ref,
                "over_percent": ((rate - ref) * 100 / ref).quantize(Decimal("0.1"), ROUND_HALF_UP)
                if rate is not None and ref
                else None,
                "over": rate is not None and ref is not None and rate > ref * (100 + over) / 100,
            }
        )
    out.sort(key=lambda r: (-(r["over_percent"] or Decimal(-1000)), r["vehicle"]["plate_number"]))
    return out
