"""The uncollected deductions balance (decision D, docs/payroll-schemes.md section 8).

A month's penalties never take the net below zero; what the pay could not cover stays on the line (the
"uncovered_penalty" cell) and, once the run is approved, becomes a line here for review («للمراجعة»). It is never
carried by itself. An accountant with payroll.approve decides each line with a written note:
- «تُرحّل للشهر التالي»: a manual deduction of that amount from the month after the run's (or this month, for an old
  run), made through the deductions module and approved by this decision;
- «إسقاط»: dropped, nothing more is taken.

Reopening a run removes its lines still under review (the next approval records them again); a line already decided
stays, and the next approval only records what was not decided yet.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.payroll import service
from app.modules.payroll.models import Deduction, Line, Run, Uncollected
from app.modules.people import service as people

ZERO = Decimal(0)
# the month's penalties, in the order the salary sheet shows them: what a line's uncollected balance comes from
PENALTIES = (
    "missing_target",
    "marks_deduction",
    "invalid_days_deduction",
    "absence_deduction",
    "cancelled_orders",
    "platform_deductions",
    "late",
    "cash_shortage",
)


def _amount(cells: dict, code: str) -> Decimal:
    return Decimal(str(cells.get(code) or 0))


def record_for_run(db: Session, run: Run, *, actor_user_id: int) -> int:
    """In the approval's transaction: a line for review for every employee whose pay could not cover the month's
    penalties, less what earlier approvals of the same run already had decided. Returns how many were recorded."""
    lines = db.scalars(select(Line).where(Line.run_id == run.id)).all()
    decided = dict(
        db.execute(
            select(Uncollected.employee_id, func.sum(Uncollected.amount))
            .where(Uncollected.run_id == run.id, Uncollected.status != "review")
            .group_by(Uncollected.employee_id)
        ).all()
    )
    n = 0
    for line in lines:
        amount = _amount(line.cells, "uncovered_penalty") - Decimal(decided.get(line.employee_id) or 0)
        if amount <= 0:
            continue
        reason = {
            "gross": str(line.gross),
            "items": [{"code": c, "amount": str(_amount(line.cells, c))} for c in PENALTIES if _amount(line.cells, c)],
        }
        u = Uncollected(
            run_id=run.id,
            employee_id=line.employee_id,
            company_id=run.company_id,
            month=run.month,
            round=run.reopened,
            amount=amount,
            reason=reason,
        )
        db.add(u)
        db.flush()
        db.refresh(u)
        audit.record(
            db,
            action="uncollected.recorded",
            entity_type="uncollected",
            entity_id=u.public_id,
            actor_user_id=actor_user_id,
            company_id=run.company_id,
            after={"month": run.month, "amount": amount, **reason},
        )
        n += 1
    return n


def clear_for_reopen(db: Session, run: Run) -> None:
    """In the reopening's transaction: the lines still under review go (the next approval records them again)."""
    for u in db.scalars(select(Uncollected).where(Uncollected.run_id == run.id, Uncollected.status == "review")):
        db.delete(u)


def _scoped(q, all_companies: bool, company_ids):
    return q if all_companies else q.where(Uncollected.company_id.in_(list(company_ids)))


def _out(db: Session, rows: list[Uncollected]) -> list[dict]:
    names = people.names(db, {u.employee_id for u in rows})
    users = identity.user_names(db, {u.decided_by for u in rows if u.decided_by})
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.id.in_([u.run_id for u in rows] or [0])))}
    deds = {
        d.id: d for d in db.scalars(select(Deduction).where(Deduction.id.in_([u.deduction_id for u in rows] or [0])))
    }
    return [
        {
            "id": str(u.public_id),
            "run": {"id": str(runs[u.run_id].public_id), "month": u.month, "status": runs[u.run_id].status},
            "employee": names.get(u.employee_id),
            "company_id": u.company_id,
            "month": u.month,
            "amount": u.amount,
            "reason": u.reason,
            "status": u.status,
            "note": u.note,
            "deduction": {
                "id": str(deds[u.deduction_id].public_id),
                "start_month": deds[u.deduction_id].start_month,
                "status": deds[u.deduction_id].status,
            }
            if u.deduction_id in deds
            else None,
            "decided_by": users.get(u.decided_by),
            "decided_at": u.decided_at,
            "created_at": u.created_at,
            "version": u.version,
        }
        for u in rows
    ]


def list_lines(
    db: Session,
    *,
    month: date | None = None,
    status: str | None = None,
    employee_public_id=None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    """The balance, per payroll month and per driver: each line's run, driver, amount and why."""
    q = _scoped(select(Uncollected), **scope)
    if month is not None:
        q = q.where(Uncollected.month == service.month_start(month))
    if status:
        q = q.where(Uncollected.status == status)
    if employee_public_id:
        q = q.where(Uncollected.employee_id == people.ref_by_public_id(db, employee_public_id, **scope).id)
    q = q.order_by(Uncollected.month.desc(), Uncollected.id.desc()).limit(limit).offset(offset)
    return _out(db, list(db.scalars(q)))


def counts(db: Session, **scope) -> dict:
    q = select(func.count(), func.coalesce(func.sum(Uncollected.amount), 0)).where(Uncollected.status == "review")
    n, total = db.execute(_scoped(q, **scope)).one()
    return {"review": n, "amount": f"{Decimal(total):.3f}"}


def _for_decision(db: Session, public_id, *, version: int | None, **scope) -> Uncollected:
    u = db.scalar(_scoped(select(Uncollected).where(Uncollected.public_id == public_id), **scope).with_for_update())
    if u is None:
        raise AppError(404, "uncollected_not_found")
    if u.status != "review":
        raise AppError(409, "uncollected_decided", status=u.status)
    if version is not None and u.version != version:
        raise AppError(409, "version_conflict")
    return u


def carry(db: Session, public_id, *, note: str, version: int | None, actor_user_id: int, **scope) -> dict:
    """Carried with the accountant's explicit approval and note: a manual deduction of the amount, from the month
    after the run's (never a month already gone), approved by this decision. The approved run does not change."""
    u = _for_decision(db, public_id, version=version, **scope)
    start = max(service.add_months(u.month, 1), service.month_start(today()))
    lang = i18n.default_language(db).code
    reason = i18n.t(db, lang, "uncollected.deduction_reason", month=u.month.strftime("%m-%Y"), note=note)
    deduction_id = service.create_deduction(
        db,
        employee_id=u.employee_id,
        company_id=u.company_id,
        source_type="other",
        source_id=u.id,
        reason=reason,
        total=u.amount,
        installments=1,
        start_month=start,
        actor_user_id=actor_user_id,
    )
    service.tell_driver(db, deduction_id)
    u.status, u.note, u.deduction_id = "carried", note, deduction_id
    u.decided_by, u.decided_at = actor_user_id, utcnow()
    u.version += 1
    audit.record(
        db,
        action="uncollected.carried",
        entity_type="uncollected",
        entity_id=u.public_id,
        actor_user_id=actor_user_id,
        company_id=u.company_id,
        after={"amount": u.amount, "from": start, "note": note},
    )
    db.commit()
    return _out(db, [u])[0]


def drop(db: Session, public_id, *, note: str, version: int | None, actor_user_id: int, **scope) -> dict:
    u = _for_decision(db, public_id, version=version, **scope)
    u.status, u.note = "dropped", note
    u.decided_by, u.decided_at = actor_user_id, utcnow()
    u.version += 1
    audit.record(
        db,
        action="uncollected.dropped",
        entity_type="uncollected",
        entity_id=u.public_id,
        actor_user_id=actor_user_id,
        company_id=u.company_id,
        after={"amount": u.amount, "note": note},
    )
    db.commit()
    return _out(db, [u])[0]
