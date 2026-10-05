"""Deductions that payroll will apply (BRD 5.14, first part: the payroll run itself comes later).

A deduction is created by the act that approves it (an accident's liability outcome, later a fine), with its source
and reason: a total in equal monthly installments from a start month, the remainder on the last one (150.000 over
3 months: 50.000 a month; 100.000 over 3: 33.333, 33.333, 33.334). One live deduction per source. Cancelled with a
reason, never deleted.

The schedule is the plan. What a month actually deducts is capped when payroll runs: at most the share of the salary
in the settings (FR-PAY-03), the rest moving to the next month (`month_deduction`). The share is the client's decision
after legal advice (BR-16) and has no default.
"""

from collections.abc import Iterable
from datetime import date
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.payroll.models import Deduction
from app.modules.people import service as people

CENT = Decimal("0.001")


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def schedule(total: Decimal, installments: int, start_month: date) -> list[dict]:
    """Equal installments rounded down to the fils, the remainder on the last one: the sum is always the total."""
    each = (total / installments).quantize(CENT, rounding=ROUND_DOWN)
    last = total - each * (installments - 1)
    return [
        {"month": add_months(start_month, i), "amount": last if i == installments - 1 else each}
        for i in range(installments)
    ]


def due_in(rows: Iterable[Deduction], month: date) -> Decimal:
    """What the plans of these deductions ask for in `month`."""
    month = month_start(month)
    return sum(
        (
            step["amount"]
            for d in rows
            for step in schedule(d.total, d.installments, d.start_month)
            if step["month"] == month
        ),
        Decimal(0),
    )


def month_cap(salary: Decimal, percent: Decimal) -> Decimal:
    """The most a month may deduct: the share of that month's salary, rounded down to the fils."""
    return (Decimal(salary) * Decimal(percent) / 100).quantize(CENT, rounding=ROUND_DOWN)


def month_deduction(due: Decimal, carried_in: Decimal, cap: Decimal) -> tuple[Decimal, Decimal]:
    """FR-PAY-03: this month deducts what is due plus what the earlier months could not, up to the cap; the rest moves
    to the next month. Returns (deducted, carried to the next month)."""
    owed = Decimal(due) + Decimal(carried_in)
    deducted = min(owed, max(Decimal(cap), Decimal(0)))
    return deducted, owed - deducted


def _out(rows: list[Deduction], db: Session) -> list[dict]:
    names = people.names(db, {d.employee_id for d in rows})
    users = identity.user_names(db, {u for d in rows for u in (d.created_by, d.cancelled_by) if u})
    return [
        {
            "id": str(d.public_id),
            "employee": names.get(d.employee_id),
            "company_id": d.company_id,
            "source_type": d.source_type,
            "reason": d.reason,
            "total": d.total,
            "installments": d.installments,
            "start_month": d.start_month,
            "schedule": schedule(d.total, d.installments, d.start_month),
            "status": d.status,
            "created_at": d.created_at,
            "created_by": users.get(d.created_by),
            "cancelled_at": d.cancelled_at,
            "cancelled_by": users.get(d.cancelled_by),
            "cancel_reason": d.cancel_reason,
        }
        for d in rows
    ]


# ------------------------------------------------------------------ for other modules (in the caller's transaction)


def create_deduction(
    db: Session,
    *,
    employee_id: int,
    company_id: int,
    source_type: str,
    source_id: int | None,
    reason: str,
    total: Decimal,
    installments: int,
    start_month: date,
    actor_user_id: int,
) -> int:
    """Approved by whoever calls it (the caller checks the permission). Returns the deduction's id."""
    total = Decimal(total).quantize(CENT)
    if total <= 0:
        raise AppError(422, "deduction_total_invalid")
    if not 1 <= installments <= 60:
        raise AppError(422, "installments_invalid")
    start_month = month_start(start_month)
    if start_month < month_start(today()):  # a closed month cannot be deducted any more
        raise AppError(422, "start_month_in_past")
    d = Deduction(
        employee_id=employee_id,
        company_id=company_id,
        source_type=source_type,
        source_id=source_id,
        reason=reason,
        total=total,
        installments=installments,
        start_month=start_month,
        created_by=actor_user_id,
    )
    db.add(d)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "deductions_one_per_source_idx":
            raise
        raise AppError(409, "deduction_exists") from None
    db.refresh(d)
    audit.record(
        db,
        action="deduction.approved",
        entity_type="deduction",
        entity_id=d.public_id,
        actor_user_id=actor_user_id,
        company_id=company_id,
        after={
            "source_type": source_type,
            "reason": reason,
            "total": total,
            "installments": installments,
            "start_month": start_month,
        },
    )
    emit(
        db,
        "payroll.deduction.approved",
        d.public_id,
        {
            "deduction_id": str(d.public_id),
            "employee_id": str(people.ref(db, employee_id).public_id),
            "source_type": source_type,
            "total": str(total),
            "installments": installments,
            "start_month": start_month.isoformat(),
        },
    )
    return d.id


def deduction(db: Session, deduction_id: int | None) -> dict | None:
    if deduction_id is None:
        return None
    d = db.get(Deduction, deduction_id)
    return _out([d], db)[0] if d else None


def for_employee(db: Session, employee_id: int) -> list[dict]:
    """What the driver sees in the app: live deductions with their monthly schedule."""
    rows = db.scalars(
        select(Deduction)
        .where(Deduction.employee_id == employee_id, Deduction.status == "approved")
        .order_by(Deduction.start_month.desc(), Deduction.id.desc())
    )
    return _out(list(rows), db)


# ------------------------------------------------------------------ the deductions screen


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Deduction.company_id.in_(list(company_ids)))


def list_deductions(
    db: Session,
    *,
    status: str | None = None,
    employee_public_id=None,
    month: date | None = None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Deduction), **scope)
    if status:
        q = q.where(Deduction.status == status)
    if employee_public_id:
        q = q.where(Deduction.employee_id == people.ref_by_public_id(db, employee_public_id, **scope).id)
    rows = list(db.scalars(q.order_by(Deduction.created_at.desc(), Deduction.id.desc())))
    if month is not None:  # the deductions that have an installment in that month
        month = month_start(month)
        rows = [d for d in rows if d.start_month <= month < add_months(d.start_month, d.installments)]
    return _out(rows[offset : offset + min(limit, 500)], db)


def cancel(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    d = db.scalar(_scoped(select(Deduction).where(Deduction.public_id == public_id), **scope).with_for_update())
    if d is None:
        raise AppError(404, "deduction_not_found")
    if d.status == "cancelled":
        raise AppError(409, "deduction_cancelled")
    d.status, d.cancel_reason, d.cancelled_by, d.cancelled_at = "cancelled", reason, actor_user_id, utcnow()
    audit.record(
        db,
        action="deduction.cancelled",
        entity_type="deduction",
        entity_id=d.public_id,
        actor_user_id=actor_user_id,
        company_id=d.company_id,
        after={"reason": reason},
    )
    emit(db, "payroll.deduction.cancelled", d.public_id, {"deduction_id": str(d.public_id), "reason": reason})
    db.commit()
    return _out([d], db)[0]


def create_manual(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    """An advance, a SIM card or another deduction the office enters itself (deductions.manage). It starts next
    month unless a start month is given; a month whose payroll is already approved moves it on by itself."""
    employee = people.ref_by_public_id(db, data["employee_id"], **scope)
    start = data.get("start_month") or add_months(month_start(today()), 1)
    deduction_id = create_deduction(
        db,
        employee_id=employee.id,
        company_id=employee.company_id,
        source_type=data["source_type"],
        source_id=None,
        reason=data["reason"],
        total=data["total"],
        installments=data["installments"],
        start_month=start,
        actor_user_id=actor_user_id,
    )
    db.commit()
    return deduction(db, deduction_id)
