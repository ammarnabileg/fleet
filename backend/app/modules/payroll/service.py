"""Deductions that payroll will apply (BRD 5.14, first part: the payroll run itself comes later).

A deduction is created by the act that approves it (an accident's liability outcome, later a fine), with its source
and reason: a total in equal monthly installments from a start month, the remainder on the last one (150.000 over
3 months: 50.000 a month; 100.000 over 3: 33.333, 33.333, 33.334). One live deduction per source. Cancelled with a
reason, never deleted.

The schedule is the plan. What a month actually deducts is capped when payroll runs: at most the share of the salary
in the settings (FR-PAY-03), the rest moving to the next month (`month_deduction`). The share is the client's decision
after legal advice (BR-16) and has no default.
"""

import logging
from collections.abc import Iterable
from datetime import date
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import business_date, today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.core.text import norm
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.payroll.models import Deduction, Line, LineDeduction, Platform, Run, Scheme
from app.modules.people import service as people

log = logging.getLogger("fleet.payroll")

CENT = Decimal("0.001")


def daily_fields(db: Session, platform_id: int | None) -> list[str] | None:
    """What a driver on this platform sends in his daily report (orders, cash, valid_day); None without a platform."""
    p = db.get(Platform, platform_id) if platform_id else None
    return list(p.daily_fields) if p else None


def platform_by_label(db: Session, label: str) -> int | None:
    """A platform as a spreadsheet names it: its code or one of its names, case and Arabic letter variants ignored
    (an active one first when two match)."""
    key = norm(label)
    for p in db.scalars(select(Platform).order_by(Platform.is_active.desc(), Platform.id)):
        if key == norm(p.code) or key in {norm(v) for v in (p.name or {}).values()}:
            return p.id
    return None


def offered_schemes(db: Session, platform_id: int | None) -> list[dict]:
    """The pay schemes a driver on this platform may choose (active, offered to drivers), with their terms."""
    from app.modules.payroll import schemas, schemes

    offered = schemes.list_schemes(db, platform_id=platform_id, offered_only=True) if platform_id else []
    return [schemas.DriverSchemeOut.model_validate(s).model_dump(mode="json") for s in offered]


def scheme_from_registration(db: Session, driver: people.EmployeeRef, scheme_public_id, *, actor_user_id: int) -> bool:
    """In the caller's transaction: the scheme the driver chose in his self-registration, from this month, unless the
    office already put him on one. False when it did, or when the choice no longer holds (the scheme was withdrawn or
    his platform changed since he sent it): the registration is still approved, and his payroll line says he has no
    scheme until the office sets one."""
    from app.modules.payroll import schemes

    if schemes.scheme_of(db, driver.id, month_start(today())) is not None:
        return False
    scheme = db.scalar(select(Scheme).where(Scheme.public_id == scheme_public_id))
    offered = scheme is not None and scheme.is_active and scheme.driver_selectable
    if not offered or scheme.platform_id != driver.platform_id:
        log.info("registration scheme choice dropped for employee %s", driver.id)
        return False
    schemes.assign(db, driver, scheme, today(), source="registration", actor_user_id=actor_user_id)
    return True


def company_covers(db: Session, employee_id: int, day: date) -> list[str]:
    """What the driver's pay scheme of that day's month puts on the company (maintenance, housing, gas, sim); nothing
    without a scheme, or when his scheme is of a platform he has left (as the payroll run ignores it)."""
    from app.modules.payroll import schemes

    scheme = schemes.scheme_of(db, employee_id, month_start(day))
    driver = people.ref(db, employee_id)
    if scheme is None or driver is None or scheme.platform_id != driver.platform_id:
        return []
    return schemes.covers_of(db, scheme, month_start(day))  # informational: who bears what, never deducted


def month_locked(db: Session, company_id: int, month: date) -> bool:
    """Whether the company's payroll for that month is approved or paid (its inputs may no longer change)."""
    from app.modules.payroll.statements import locked_months

    month = month_start(month)
    return (company_id, month) in locked_months(db, [(company_id, month)])


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
    pending: bool = False,
) -> int:
    """Approved by whoever calls it (the caller checks the permission), or pending until its approval workflow
    decides (a manual deduction). Returns the deduction's id."""
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
        status="pending" if pending else "approved",
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
    if pending:
        audit.record(
            db,
            action="deduction.requested",
            entity_type="deduction",
            entity_id=d.public_id,
            actor_user_id=actor_user_id,
            company_id=company_id,
            after=_terms(d),
        )
    else:
        _approved(db, d, actor_user_id)
    return d.id


def _terms(d: Deduction) -> dict:
    return {
        "source_type": d.source_type,
        "reason": d.reason,
        "total": d.total,
        "installments": d.installments,
        "start_month": d.start_month,
    }


def _approved(db: Session, d: Deduction, actor_user_id: int) -> None:
    d.status = "approved"
    audit.record(
        db,
        action="deduction.approved",
        entity_type="deduction",
        entity_id=d.public_id,
        actor_user_id=actor_user_id,
        company_id=d.company_id,
        after=_terms(d),
    )
    emit(
        db,
        "payroll.deduction.approved",
        d.public_id,
        {
            "deduction_id": str(d.public_id),
            "employee_id": str(people.ref(db, d.employee_id).public_id),
            "source_type": d.source_type,
            "total": str(d.total),
            "installments": d.installments,
            "start_month": d.start_month.isoformat(),
        },
    )


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


def books_day(d: Deduction) -> date:
    """The day a deduction enters the books (and an advance leaves the treasury): the day it was made, unless it
    was approved after that day was closed (books_date)."""
    return d.books_date or business_date(d.created_at)


def _pay_advance(db: Session, d: Deduction, employee: people.EmployeeRef, actor_user_id: int) -> None:
    """An advance approved is cash out of the employee's branch treasury, when the books pay advances from the
    treasury (role deduction_advance on the treasury's account, the default): the treasury on screen goes down with
    the books, and an advance the treasury cannot cover is refused (treasury_insufficient)."""
    from app.modules.cash import service as cash
    from app.modules.finance import service as finance

    if d.source_type != "advance" or not finance.advances_from_treasury(db):
        return
    day = books_day(d)  # the day its entry in the books takes (deductions_for_posting)
    finance.check_books_date(db, day)
    lang = i18n.default_language(db).code
    cash.disburse(
        db,
        branch_id=employee.branch_id,
        amount=d.total,
        business_date=day,
        source_type="deduction",
        source_id=d.id,
        reason=f"{i18n.t(db, lang, 'deduction_source.advance')} · {i18n.pick(employee.name, lang, lang)}",
        actor_user_id=actor_user_id,
    )


def _taken(db: Session, deduction_id: int) -> Decimal:
    """What approved (or paid) payroll runs took of a deduction."""
    return db.scalar(
        select(func.coalesce(func.sum(LineDeduction.deducted), 0))
        .join(Line, Line.id == LineDeduction.line_id)
        .join(Run, Run.id == Line.run_id)
        .where(LineDeduction.deduction_id == deduction_id, Run.status.in_(("approved", "paid")))
    )


def taken_by_payroll(db: Session, deduction_id: int) -> Decimal:
    return _taken(db, deduction_id)


def cancel_untaken(db: Session, deduction_id: int, *, reason: str, actor_user_id: int) -> None:
    """In the caller's transaction: a deduction no approved payroll took anything of, cancelled (the uncollected
    balance of a run that is reopened, carried to the next month: the next approval records it afresh)."""
    d = db.scalar(select(Deduction).where(Deduction.id == deduction_id).with_for_update())
    if d is None or d.status in ("cancelled", "rejected"):
        return
    if _taken(db, d.id):
        raise AppError(409, "deduction_partly_taken")
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


def cancel(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """Cancelled with a reason (the row locked: a payroll run approving at the same moment locks its advances too).
    An approved advance cancelled before any approved payroll took of it gives all of it back to its treasury (its
    disbursement reversed); once payroll took part, it is refused: corrected with a manual entry or an adjustment,
    so the treasury on screen and the books never part."""
    from app.modules.cash import service as cash

    d = db.scalar(_scoped(select(Deduction).where(Deduction.public_id == public_id), **scope).with_for_update())
    if d is None:
        raise AppError(404, "deduction_not_found")
    if d.status in ("cancelled", "rejected"):
        raise AppError(409, "deduction_cancelled")
    if d.status == "approved" and d.source_type == "advance":
        taken = _taken(db, d.id)
        if taken:
            raise AppError(409, "advance_partly_recovered", taken=f"{taken:.3f}")
        cash.undo_disbursement(db, source_type="deduction", source_id=d.id, reason=reason, actor_user_id=actor_user_id)
    if d.status == "pending":  # withdrawn before its workflow decided
        approvals.withdrawn(db, "manual_deduction", [d.id])
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
        pending=True,
    )
    d = db.get(Deduction, deduction_id)
    # with an approval workflow for the amount it waits for its last step (BRD FR-WFL-02); otherwise it applies now
    if not approvals.submitted(db, "manual_deduction", **_approval(db, d, employee), actor_user_id=actor_user_id):
        _approved(db, d, actor_user_id)
        _pay_advance(db, d, employee, actor_user_id)
        _tell_driver(db, d)
    db.commit()
    return deduction(db, deduction_id)


def _approval(db: Session, d: Deduction, employee: people.EmployeeRef) -> dict:
    lang = i18n.default_language(db).code
    return {
        "document_id": d.id,
        "document_key": d.public_id,
        "document_ref": f"{i18n.pick(employee.name, lang, lang)} {d.total:.3f}",
        "company_id": d.company_id,
        "amount": d.total,
    }


def _tell_driver(db: Session, d: Deduction) -> None:
    notifications.notify_driver(
        db,
        d.employee_id,
        "deduction_added",
        params={"reason": d.reason, "amount": f"{d.total:.3f}", "installments": d.installments},
        entity_type="deduction",
    )


def tell_driver(db: Session, deduction_id: int) -> None:
    """The driver's notice of a deduction approved by another act (an uncollected balance carried)."""
    _tell_driver(db, db.get(Deduction, deduction_id))


def _books_day_on_approval(db: Session, d: Deduction, employee: people.EmployeeRef) -> None:
    """It enters the books on the day it was made; when that day's month is closed (or, for an advance paid from the
    treasury, the treasury's day is closed by its count) it enters them, and leaves the treasury, on the day it is
    approved: kept as its books date, so the entry and the treasury movement carry the same date."""
    from app.modules.cash import service as cash
    from app.modules.finance import service as finance

    made = business_date(d.created_at)
    if made == today():
        return
    closed = finance.month_closed(db, made)
    if not closed and d.source_type == "advance" and finance.advances_from_treasury(db):
        last = cash.last_closed_day(db, [employee.branch_id])
        closed = last is not None and made <= last
    if closed:
        d.books_date = today()


def decide_manual(db: Session, public_id, *, approve: bool, reason: str | None, actor_user_id: int, **scope) -> dict:
    """A step of a pending manual deduction's workflow, from the approvals inbox. Approved after its first month has
    passed, it starts with the current month; refused, it keeps the reason and is never deducted."""
    d = db.scalar(_scoped(select(Deduction).where(Deduction.public_id == public_id), **scope).with_for_update())
    if d is None:
        raise AppError(404, "deduction_not_found")
    if d.status != "pending":
        raise AppError(409, "deduction_decided", status=d.status)
    employee = people.ref(db, d.employee_id)
    if approve:
        _books_day_on_approval(db, d, employee)
    if approvals.gate(
        db,
        "manual_deduction",
        **_approval(db, d, employee),
        actor_user_id=actor_user_id,
        approve=approve,
        reason=reason,
    ):
        if approve:
            d.start_month = max(d.start_month, month_start(today()))
            _approved(db, d, actor_user_id)
            _pay_advance(db, d, employee, actor_user_id)
            _tell_driver(db, d)
        else:
            d.status, d.cancel_reason, d.cancelled_by, d.cancelled_at = "rejected", reason, actor_user_id, utcnow()
            audit.record(
                db,
                action="deduction.rejected",
                entity_type="deduction",
                entity_id=d.public_id,
                actor_user_id=actor_user_id,
                company_id=d.company_id,
                comment=reason,
            )
    db.commit()
    return _out([d], db)[0]


# ------------------------------------------------------------------ for finance


def approve_run(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    from app.modules.payroll import runs

    return runs.approve(db, public_id, actor_user_id=actor_user_id, **scope)


def send_back_run(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    from app.modules.payroll import runs

    return runs.send_back(db, public_id, reason=reason, actor_user_id=actor_user_id, **scope)


def runs_for_posting(db: Session, first: date, last: date) -> dict[str, list[dict]]:
    from app.modules.payroll import runs

    return runs.runs_for_posting(db, first, last)


def deduction_employees(db: Session, deduction_ids) -> dict[int, int]:
    """The employee of each deduction, for finance's account statements."""
    ids = list(set(deduction_ids))
    if not ids:
        return {}
    return dict(db.execute(select(Deduction.id, Deduction.employee_id).where(Deduction.id.in_(ids))).all())


def deductions_for_posting(db: Session, first: date, last: date) -> list[dict]:
    from app.modules.payroll import runs

    return runs.deductions_for_posting(db, first, last)


def platform_is_active(db: Session, platform_id: int) -> bool:
    p = db.get(Platform, platform_id)
    return bool(p and p.is_active)


def platform_name(db: Session, platform_id: int | None) -> dict | None:
    p = db.get(Platform, platform_id) if platform_id else None
    return p.name if p else None


def pending_for_close(db: Session, first: date, last: date) -> dict[str, int]:
    """For the books' month close: the deductions made first..last still waiting for their workflow, and the runs of
    that month still drafts (each enters the books in that month once decided)."""
    made_on = func.date(func.timezone("Asia/Kuwait", Deduction.created_at))
    return {
        "deductions": db.scalar(
            select(func.count())
            .select_from(Deduction)
            .where(made_on.between(first, last), Deduction.status == "pending")
        ),
        "runs": db.scalar(
            select(func.count()).select_from(Run).where(Run.month.between(first, last), Run.status == "draft")
        ),
    }
