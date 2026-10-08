"""Fuel a driver paid from the cash he holds (the client's decision, docs: fuel claims).

The driver claims it from the app: the amount, a camera photo of the receipt (each receipt once) and, if he wants, the
odometer. The accountant reviews it, usually when he receives the driver's cash: he approves it (and may correct the
amount, with a note) or rejects it with a reason.

Only when the driver's pay scheme puts fuel on the company (`company_covers` holds "gas") does the approved amount
lower the cash he holds: a posted cash journal of kind "fuel" (driver -X, fuel +X), entered in the books as
Dr fuel expense / Cr drivers' cash. When fuel is on the driver nothing is recorded at all: the app does not offer it
and the server refuses it. A driver with a company fuel card claims nothing either: the cards are topped up as one
lump finance expense, not per driver. A wrong approval is undone by reversing its journal.
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, business_date, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.cash import service as cash
from app.modules.cash.models import FuelClaim, Journal
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.payroll import service as payroll
from app.modules.people import service as people

CLOCK_SKEW = timedelta(minutes=5)
OLDEST = timedelta(days=7)  # an older receipt is no longer claimed
ERRORS = {"fuel_claims_client_ref_key": "fuel_exists", "fuel_claims_receipt_sha256_key": "fuel_receipt_used"}
REFUSALS = {"fuel_card": "fuel_card_driver", "not_covered": "fuel_not_covered", "no_vehicle": "fuel_no_vehicle"}


def _covered(db: Session, driver: people.EmployeeRef, day: date) -> bool:
    """The company pays his fuel: no fuel card, and his scheme of that day's month covers it."""
    return not driver.fuel_card and "gas" in payroll.company_covers(db, driver.id, day)


def _refusal(db: Session, driver: people.EmployeeRef, day: date) -> str | None:
    if driver.fuel_card:
        return "fuel_card"
    if "gas" not in payroll.company_covers(db, driver.id, day):
        return "not_covered"
    return None


def _max_amount(db: Session) -> Decimal:
    return org.get_section(db, "cash").fuel_max_amount


def _driver_out(db: Session, rows: list[FuelClaim]) -> list[dict]:
    plates = fleet.plate_numbers(db, {c.vehicle_id for c in rows})
    return [
        {
            "id": str(c.public_id),
            "paid_at": c.paid_at,
            "amount": c.amount,
            "approved_amount": c.approved_amount,
            "status": c.status,
            "decision_note": c.decision_note,
            "odometer_km": c.odometer_km,
            "notes": c.notes,
            "vehicle_plate": plates.get(c.vehicle_id),
            "created_at": c.created_at,
        }
        for c in rows
    ]


# ------------------------------------------------------------------ the driver


def driver_view(db: Session, employee_id: int) -> dict:
    """Whether the app offers him fuel now (and why not), the most a claim may be, and his last claims."""
    driver = people.ref(db, employee_id)
    reason = _refusal(db, driver, business_date(utcnow()))
    if reason is None and fleet.open_custody_for_driver(db, employee_id) is None:
        reason = "no_vehicle"
    rows = list(
        db.scalars(
            select(FuelClaim)
            .where(FuelClaim.employee_id == employee_id)
            .order_by(FuelClaim.paid_at.desc(), FuelClaim.id.desc())
            .limit(30)
        )
    )
    return {
        "allowed": reason is None,
        "reason": reason,
        "max_amount": _max_amount(db),
        "claims": _driver_out(db, rows),
    }


def _check_receipt(db: Session, sha: str, device_id: int) -> None:
    """A photo this phone took with its camera (as an accident's photos), never claimed before."""
    info = files.get(db, sha)
    if info.content_type not in files.IMAGES:
        raise AppError(422, "photo_must_be_image")
    if info.uploaded_by_device != device_id or info.source != "camera":
        raise AppError(422, "file_not_yours")
    if db.scalar(select(FuelClaim.id).where(FuelClaim.receipt_sha256 == sha)):
        raise AppError(409, "fuel_receipt_used")


def driver_claim(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    if db.scalar(select(FuelClaim.id).where(FuelClaim.client_ref == data["client_ref"])):
        raise AppError(409, "fuel_exists")  # a resend: already recorded
    driver = people.ref(db, employee_id)
    at: datetime = data["paid_at"]
    if at.tzinfo is None:
        at = at.replace(tzinfo=KUWAIT)
    now = utcnow()
    if at > now + CLOCK_SKEW:
        raise AppError(422, "time_in_future")
    if at < now - OLDEST:
        raise AppError(422, "fuel_too_old", days=OLDEST.days)
    reason = _refusal(db, driver, business_date(at))
    if reason is not None:
        raise AppError(409, REFUSALS[reason])
    custody = next(iter(fleet.custodies_for_driver(db, employee_id, at, at)), None)
    if custody is None:
        raise AppError(409, "fuel_no_vehicle")
    limit = _max_amount(db)
    if data["amount"] > limit:
        raise AppError(422, "fuel_amount_too_high", max=f"{limit:.3f}")
    _check_receipt(db, data["receipt_sha256"], device_id)
    claim = FuelClaim(
        employee_id=employee_id,
        company_id=driver.company_id,
        branch_id=driver.branch_id,
        vehicle_id=custody.vehicle_id,
        client_ref=data["client_ref"],
        paid_at=at,
        amount=data["amount"],
        odometer_km=data.get("odometer_km"),
        receipt_sha256=data["receipt_sha256"],
        notes=data.get("notes") or None,
    )
    try:
        with db.begin_nested():
            db.add(claim)
            db.flush()
    except IntegrityError as exc:
        code = ERRORS.get(violated_constraint(exc) or "")
        if code:
            raise AppError(409, code) from None
        raise
    db.refresh(claim)
    notifications.raise_alert(
        db,
        "fuel_claim",
        company_id=claim.company_id,
        entity_type="fuel_claim",
        entity_id=claim.public_id,
        params={"name": driver.name, "amount": f"{claim.amount:.3f}"},
        dedupe_key=_alert_key(claim),
    )
    audit.record(
        db,
        action="cash.fuel_claimed",
        entity_type="fuel_claim",
        entity_id=claim.public_id,
        actor_type="device",
        company_id=claim.company_id,
        after={"driver": str(driver.public_id), "amount": claim.amount, "paid_at": at.isoformat()},
    )
    db.commit()
    return _driver_out(db, [claim])[0]


def _alert_key(claim: FuelClaim) -> str:
    return f"fuel_claim:{claim.id}"


# ------------------------------------------------------------------ the office


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(FuelClaim.company_id.in_(list(company_ids)))


def _office_out(db: Session, rows: list[FuelClaim]) -> list[dict]:
    plates = fleet.plate_numbers(db, {c.vehicle_id for c in rows})
    refs = {e: people.ref(db, e) for e in {c.employee_id for c in rows}}
    deciders = identity.user_names(db, {c.decided_by for c in rows if c.decided_by})
    journals = dict(
        db.execute(
            select(Journal.id, Journal.public_id).where(Journal.id.in_([c.journal_id for c in rows if c.journal_id]))
        ).all()
    )
    covered: dict[tuple[int, date], bool] = {}
    out = []
    for c in rows:
        month = business_date(c.paid_at).replace(day=1)
        key = (c.employee_id, month)
        if key not in covered:
            covered[key] = _covered(db, refs[c.employee_id], business_date(c.paid_at))
        ref = refs[c.employee_id]
        out.append(
            {
                "id": str(c.public_id),
                "driver": {"id": str(ref.public_id), "name": ref.name},
                "company_id": c.company_id,
                "branch_id": c.branch_id,
                "vehicle_plate": plates.get(c.vehicle_id),
                "paid_at": c.paid_at,
                "amount": c.amount,
                "approved_amount": c.approved_amount,
                "odometer_km": c.odometer_km,
                "notes": c.notes,
                "status": c.status,
                "decision_note": c.decision_note,
                "decided_by": deciders.get(c.decided_by),
                "decided_at": c.decided_at,
                "covered": covered[key],
                "fuel_card": ref.fuel_card,
                "journal_id": str(journals[c.journal_id]) if c.journal_id else None,
                "receipt_url": f"/api/v1/cash/fuel-claims/{c.public_id}/receipt",
                "created_at": c.created_at,
            }
        )
    return out


def list_claims(
    db: Session,
    *,
    status: str | None = None,
    driver_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
    all_companies: bool,
    company_ids: Iterable[int],
) -> list[dict]:
    q = _scoped(select(FuelClaim), all_companies, company_ids)
    if status:
        q = q.where(FuelClaim.status == status)
    if driver_id:
        q = q.where(FuelClaim.employee_id == driver_id)
    if date_from:
        q = q.where(FuelClaim.paid_at >= datetime.combine(date_from, datetime.min.time(), KUWAIT))
    if date_to:
        q = q.where(FuelClaim.paid_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), KUWAIT))
    q = q.order_by(FuelClaim.paid_at.desc(), FuelClaim.id.desc()).limit(min(limit, 500))
    return _office_out(db, list(db.scalars(q)))


def pending_count(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> int:
    q = _scoped(select(func.count()).select_from(FuelClaim), all_companies, company_ids)
    return db.scalar(q.where(FuelClaim.status == "pending"))


def _get(db: Session, public_id, *, lock: bool = False, all_companies: bool, company_ids: Iterable[int]) -> FuelClaim:
    q = _scoped(select(FuelClaim).where(FuelClaim.public_id == public_id), all_companies, company_ids)
    claim = db.scalar(q.with_for_update() if lock else q)
    if claim is None:
        raise AppError(404, "fuel_claim_not_found")
    return claim


def receipt(db: Session, public_id, **scope) -> files.FileInfo:
    return files.get(db, _get(db, public_id, **scope).receipt_sha256)


def _decided(db: Session, claim: FuelClaim, **values) -> None:
    """Conditional on pending: a claim is decided once, whoever comes second is told so."""
    done = db.execute(
        update(FuelClaim).where(FuelClaim.id == claim.id, FuelClaim.status == "pending").values(**values)
    ).rowcount
    if done != 1:
        raise AppError(409, "fuel_decided")


def approve(db: Session, public_id, *, amount: Decimal | None, note: str | None, actor_user_id: int, **scope) -> dict:
    claim = _get(db, public_id, lock=True, **scope)
    if claim.status != "pending":
        raise AppError(409, "fuel_decided", status=claim.status)
    amount = claim.amount if amount is None else amount
    if amount != claim.amount and not note:
        raise AppError(422, "reason_required")  # a corrected amount says why
    limit = _max_amount(db)
    if amount > limit:
        raise AppError(422, "fuel_amount_too_high", max=f"{limit:.3f}")
    driver = people.ref(db, claim.employee_id)
    day = business_date(claim.paid_at)
    reason = _refusal(db, driver, day)
    if reason is not None:  # his scheme or his card changed since he claimed: the claim can only be rejected now
        raise AppError(409, REFUSALS[reason])
    journal = cash._journal(
        db,
        "fuel",
        source_type="fuel_claim",
        source_id=claim.id,
        lines=[(cash.account(db, "driver", driver_id=driver.id), -amount), (cash.account(db, "fuel"), amount)],
        actor_user_id=actor_user_id,
        reason=note,
        post=True,
        business_date=day,
        attachment_sha256=claim.receipt_sha256,
    )
    _decided(
        db,
        claim,
        status="approved",
        approved_amount=amount,
        decision_note=note,
        decided_by=actor_user_id,
        decided_at=utcnow(),
        journal_id=journal.id,
    )
    cash.check_balance_alert(db, driver)
    notifications.resolve(db, _alert_key(claim))
    notifications.notify_driver(
        db,
        driver.id,
        "fuel_approved",
        params={"amount": f"{amount:.3f}"},
        entity_type="fuel_claim",
        entity_id=claim.public_id,
    )
    audit.record(
        db,
        action="cash.fuel_approved",
        entity_type="fuel_claim",
        entity_id=claim.public_id,
        actor_user_id=actor_user_id,
        company_id=claim.company_id,
        before={"amount": claim.amount},
        after={"amount": amount, "journal": str(journal.public_id)},
        comment=note,
    )
    db.commit()
    db.refresh(claim)
    return _office_out(db, [claim])[0]


def reject(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    claim = _get(db, public_id, lock=True, **scope)
    if claim.status != "pending":
        raise AppError(409, "fuel_decided", status=claim.status)
    _decided(db, claim, status="rejected", decision_note=reason, decided_by=actor_user_id, decided_at=utcnow())
    notifications.resolve(db, _alert_key(claim))
    notifications.notify_driver(
        db,
        claim.employee_id,
        "fuel_rejected",
        params={"reason": reason},
        entity_type="fuel_claim",
        entity_id=claim.public_id,
    )
    audit.record(
        db,
        action="cash.fuel_rejected",
        entity_type="fuel_claim",
        entity_id=claim.public_id,
        actor_user_id=actor_user_id,
        company_id=claim.company_id,
        comment=reason,
    )
    db.commit()
    db.refresh(claim)
    return _office_out(db, [claim])[0]
