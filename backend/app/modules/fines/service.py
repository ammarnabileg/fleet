"""Traffic fines (BRD FR-VEH-06, FR-PAY-02; UAT-12 in practice: a fine at a given time names who was driving).

A fine is registered with the time on the ticket; the driver responsible is whoever held the vehicle then, from the
custody log (none if nobody did: alerted, and it cannot be charged). It is decided once: charged to the driver as an
approved deduction in monthly installments (deductions.manage), borne by the company with a reason, or cancelled as a
wrong entry. If the driver's deduction is later cancelled (from the deductions page), the fine can be decided again.
Paying the traffic department is recorded apart (finance), whatever the decision. A ticket number is entered once.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import KUWAIT, today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.fines.models import Fine
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.payroll import service as payroll
from app.modules.people import service as people

ERRORS = {"fines_reference_no_idx": "fine_exists"}
CLOCK_SKEW = timedelta(minutes=5)
OLDEST = timedelta(days=5 * 365)  # tickets surface late (at the registration renewal), but not that late


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Fine.company_id.in_(list(company_ids)))


def _get(db: Session, public_id, *, lock=False, all_companies: bool, company_ids: Iterable[int]) -> Fine:
    q = _scoped(select(Fine).where(Fine.public_id == public_id), all_companies, company_ids)
    f = db.scalar(q.with_for_update() if lock else q)
    if f is None:
        raise AppError(404, "fine_not_found")
    return f


def _deduction(db: Session, f: Fine) -> dict | None:
    return payroll.deduction(db, f.deduction_id)


def _can_decide(f: Fine, deduction: dict | None) -> bool:
    """Open, or charged whose deduction was cancelled since: decided again."""
    return f.status == "open" or (
        f.status == "charged" and deduction is not None and deduction["status"] == "cancelled"
    )


def _out(db: Session, rows: list[Fine]) -> list[dict]:
    cards = fleet.vehicle_cards(db, {f.vehicle_id for f in rows})
    names = people.names(db, {f.driver_id for f in rows if f.driver_id})
    users = identity.user_names(db, {u for f in rows for u in (f.decided_by, f.paid_by, f.created_by) if u})
    out = []
    for f in rows:
        d = _deduction(db, f)
        out.append(
            {
                "id": str(f.public_id),
                "number": f.number,
                "vehicle": cards.get(f.vehicle_id, {}),
                "company_id": f.company_id,
                "driver": names.get(f.driver_id),
                "occurred_at": f.occurred_at,
                "reference_no": f.reference_no,
                "violation": f.violation,
                "location_text": f.location_text,
                "amount": f.amount,
                "has_file": f.file_sha256 is not None,
                "file_sha256": f.file_sha256,
                "notes": f.notes,
                "status": f.status,
                "can_decide": _can_decide(f, d),
                "decided_at": f.decided_at,
                "decided_by": users.get(f.decided_by),
                "decision_note": f.decision_note,
                "deduction": d,
                "paid_at": f.paid_at,
                "paid_by": users.get(f.paid_by),
                "payment_ref": f.payment_ref,
                "created_at": f.created_at,
                "created_by": users.get(f.created_by),
                "cancel_reason": f.cancel_reason,
                "version": f.version,
            }
        )
    return out


def _audit(db: Session, action: str, f: Fine, *, actor_user_id: int, after=None) -> None:
    audit.record(
        db,
        action=action,
        entity_type="fine",
        entity_id=f.public_id,
        actor_user_id=actor_user_id,
        company_id=f.company_id,
        after={"number": f.number, "status": f.status, "amount": f.amount} | (after or {}),
    )


def _emit(db: Session, event_type: str, f: Fine, **payload) -> None:
    emit(
        db,
        event_type,
        f.public_id,
        {"fine_id": str(f.public_id), "number": f.number, "amount": str(f.amount)} | payload,
    )


# ------------------------------------------------------------------ registering


def create(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope)
    at: datetime = data["occurred_at"]
    now = utcnow()
    if at > now + CLOCK_SKEW:
        raise AppError(422, "time_in_future")
    if at < now - OLDEST:
        raise AppError(422, "time_too_old")
    if data.get("file_sha256"):
        files.get(db, data["file_sha256"])  # a scan or a photo of the ticket
    custody = fleet.custody_ref_at(db, vehicle.id, at)
    f = Fine(
        vehicle_id=vehicle.id,
        company_id=vehicle.company_id,
        driver_id=custody.driver_id if custody else None,
        custody_id=custody.id if custody else None,
        occurred_at=at,
        reference_no=data.get("reference_no"),
        violation=data["violation"],
        location_text=data.get("location_text"),
        amount=data["amount"],
        file_sha256=data.get("file_sha256"),
        notes=data.get("notes"),
        created_by=actor_user_id,
    )
    db.add(f)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        code = ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None
    db.refresh(f)
    if custody is None:  # nobody held the vehicle then: someone must find out who had it
        notifications.raise_alert(
            db,
            "fine_no_driver",
            company_id=f.company_id,
            entity_type="fine",
            entity_id=f.public_id,
            params={
                "plate": vehicle.plate_number,
                "number": f.number,
                "at": at.astimezone(KUWAIT).strftime("%d-%m-%Y %H:%M"),
            },
            dedupe_key=f"fine_no_driver:{f.id}",
        )
    _audit(db, "fine.registered", f, actor_user_id=actor_user_id, after={"driver_found": custody is not None})
    _emit(db, "fine.registered", f, vehicle_id=str(vehicle.public_id), occurred_at=at.isoformat())
    db.commit()
    return _out(db, [f])[0]


def list_fines(
    db: Session,
    *,
    status: str | None = None,
    unpaid: bool = False,
    no_driver: bool = False,
    vehicle_public_id=None,
    driver_public_id=None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Fine), **scope)
    if status:
        q = q.where(Fine.status.in_(status.split(",")))
    if unpaid:  # still owed to the traffic department
        q = q.where(Fine.paid_at.is_(None), Fine.status != "cancelled")
    if no_driver:
        q = q.where(Fine.driver_id.is_(None), Fine.status == "open")
    if vehicle_public_id:
        q = q.where(Fine.vehicle_id == fleet.vehicle_ref_by_public_id(db, vehicle_public_id, **scope).id)
    if driver_public_id:
        q = q.where(Fine.driver_id == people.ref_by_public_id(db, driver_public_id, **scope).id)
    rows = db.scalars(q.order_by(Fine.occurred_at.desc(), Fine.id.desc()).limit(min(limit, 500)).offset(offset))
    return _out(db, list(rows))


def get(db: Session, public_id, **scope) -> dict:
    return _out(db, [_get(db, public_id, **scope)])[0]


def fine_file(db: Session, public_id, **scope) -> files.FileInfo:
    f = _get(db, public_id, **scope)
    if f.file_sha256 is None:
        raise AppError(404, "file_not_found")
    return files.get(db, f.file_sha256)


# ------------------------------------------------------------------ deciding


def _decidable(db: Session, f: Fine) -> None:
    if not _can_decide(f, _deduction(db, f)):
        raise AppError(409, "fine_not_open", status=f.status)


def charge(db: Session, public_id, *, data: dict, actor_user_id: int, **scope) -> dict:
    """Charged to the driver who held the vehicle: an approved deduction of the fine's amount in installments."""
    f = _get(db, public_id, lock=True, **scope)
    _decidable(db, f)
    if f.driver_id is None:
        raise AppError(409, "fine_has_no_driver")
    f.deduction_id = payroll.create_deduction(
        db,
        employee_id=f.driver_id,
        company_id=f.company_id,
        source_type="fine",
        source_id=f.id,
        reason=data.get("reason") or (f"#{f.number} {f.violation}")[:200],
        total=f.amount,
        installments=data["installments"],
        start_month=data.get("start_month") or payroll.add_months(today(), 1),
        actor_user_id=actor_user_id,
    )
    f.status, f.decided_by, f.decided_at, f.decision_note = "charged", actor_user_id, utcnow(), data.get("reason")
    f.version += 1
    notifications.resolve(db, f"fine_no_driver:{f.id}")
    _audit(db, "fine.charged", f, actor_user_id=actor_user_id, after={"installments": data["installments"]})
    _emit(db, "fine.charged", f, installments=data["installments"])
    db.commit()
    return _out(db, [f])[0]


def company_pays(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """The company bears it (the driver was not at fault, or nobody can be charged), with the reason."""
    f = _get(db, public_id, lock=True, **scope)
    _decidable(db, f)
    f.status, f.decided_by, f.decided_at, f.decision_note = "company", actor_user_id, utcnow(), reason
    f.deduction_id = None  # a cancelled deduction stays in payroll's history with its source
    f.version += 1
    notifications.resolve(db, f"fine_no_driver:{f.id}")
    _audit(db, "fine.company", f, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _out(db, [f])[0]


def cancel(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """A wrong entry. Not while a live deduction comes from it: cancel that first, from the deductions page."""
    f = _get(db, public_id, lock=True, **scope)
    if f.status == "cancelled":
        raise AppError(409, "fine_not_open", status=f.status)
    d = _deduction(db, f)
    if d is not None and d["status"] == "approved":
        raise AppError(409, "fine_charged")
    f.status, f.cancel_reason = "cancelled", reason
    f.version += 1
    notifications.resolve(db, f"fine_no_driver:{f.id}")
    _audit(db, "fine.cancelled", f, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _out(db, [f])[0]


def mark_paid(db: Session, public_id, *, payment_ref: str | None, actor_user_id: int, **scope) -> dict:
    """The company paid the traffic department (whoever finally bears it)."""
    f = _get(db, public_id, lock=True, **scope)
    if f.status == "cancelled":
        raise AppError(409, "fine_not_open", status=f.status)
    if f.paid_at is not None:
        raise AppError(409, "fine_paid")
    f.paid_at, f.paid_by, f.payment_ref = utcnow(), actor_user_id, payment_ref
    f.version += 1
    _audit(db, "fine.paid", f, actor_user_id=actor_user_id, after={"payment_ref": payment_ref})
    _emit(db, "fine.paid", f, payment_ref=payment_ref)
    db.commit()
    return _out(db, [f])[0]


# ------------------------------------------------------------------ the driver and the dashboard


def for_driver(db: Session, employee_id: int, *, limit: int = 30) -> list[dict]:
    """The driver's fines (not the cancelled ones), with the deduction when charged."""
    rows = list(
        db.scalars(
            select(Fine)
            .where(Fine.driver_id == employee_id, Fine.status != "cancelled")
            .order_by(Fine.occurred_at.desc(), Fine.id.desc())
            .limit(limit)
        )
    )
    plates = fleet.plate_numbers(db, {f.vehicle_id for f in rows})
    out = []
    for f in rows:
        d = _deduction(db, f)
        out.append(
            {
                "id": str(f.public_id),
                "number": f.number,
                "vehicle_plate": plates.get(f.vehicle_id, ""),
                "occurred_at": f.occurred_at,
                "violation": f.violation,
                "location_text": f.location_text,
                "amount": f.amount,
                "status": f.status,
                "deduction": d if d is not None and d["status"] == "approved" else None,
            }
        )
    return out


def counts(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> dict:
    """Dashboard: fines waiting for a decision, those with no driver, and what is still owed to the authority."""
    base = _scoped(
        select(func.count(), func.coalesce(func.sum(Fine.amount), 0)).select_from(Fine), all_companies, company_ids
    )
    open_n, _ = db.execute(base.where(Fine.status == "open")).one()
    no_driver, _ = db.execute(base.where(Fine.status == "open", Fine.driver_id.is_(None))).one()
    unpaid_n, unpaid_total = db.execute(base.where(Fine.status != "cancelled", Fine.paid_at.is_(None))).one()
    return {"open": open_n, "no_driver": no_driver, "unpaid": unpaid_n, "unpaid_total": str(unpaid_total)}


# ------------------------------------------------------------------ for finance


def paid_for_posting(db: Session, first, last) -> list[dict]:
    """Fines paid to the traffic department on Kuwait days first..last: finance enters each once."""
    paid_on = func.date(func.timezone("Asia/Kuwait", Fine.paid_at))
    rows = db.execute(select(Fine, paid_on).where(Fine.paid_at.is_not(None), paid_on.between(first, last))).all()
    return [
        {
            "id": f.id,
            "number": f.number,
            "company_id": f.company_id,
            "amount": f.amount,
            "violation": f.violation,
            "date": day,
            "payment_ref": f.payment_ref,
        }
        for f, day in rows
    ]
