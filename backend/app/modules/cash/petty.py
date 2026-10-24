"""What a petty cash holder spends from his custody, recorded from the driver app (the client's request: a custody
screen in the app, where he spends from it with the amount and the invoice's photo).

The holder sends the amount (3 decimals), the expense type (one the office allows for petty cash), the invoice's
camera photo (taken by this phone, each invoice once), its date and, if he wants, the vendor and a note. Nothing moves
yet: the request waits for the office. A request for more than he can still spend (his custody's balance less what he
already asked and the office has not decided) is refused: a custody is never overspent.

The office approves it: a finance expense of that type, paid from his custody (payment method petty), is created and
decided in the same transaction, which takes the money off his custody through the existing posting (petty -X,
disbursements +X, and the expense's own entry). When expenses go through an approval workflow, the request stays
"in_review" until its last step, then follows the expense (approved, rejected, or cancelled later: then the money is
back in his custody and the request reads rejected with the reason). Or the office rejects it with a reason. He may
cancel it while it is pending.
"""

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.cash import service as cash
from app.modules.cash.models import Account, Journal, JournalLine, PettyExpense
from app.modules.files import service as files
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.people import service as people

OLDEST = timedelta(days=30)  # an older invoice is not spent from the custody from the app
ERRORS = {
    "petty_expenses_client_ref_key": "petty_expense_exists",
    "petty_expenses_invoice_sha256_key": "petty_invoice_used",
}
OPEN = ("pending",)  # still counted against what he can spend: in_review already has its expense


def _types(db: Session) -> list:
    from app.modules.finance.models import ExpenseType

    return list(
        db.scalars(
            select(ExpenseType)
            .where(ExpenseType.active, ExpenseType.petty)
            .order_by(ExpenseType.sort_order, ExpenseType.id)
        )
    )


def _type_names(db: Session, ids: Iterable[int]) -> dict[int, dict]:
    from app.modules.finance.models import ExpenseType

    ids = set(ids)
    if not ids:
        return {}
    found = db.scalars(select(ExpenseType).where(ExpenseType.id.in_(ids)))
    return {t.id: {"id": t.id, "code": t.code, "name": t.name} for t in found}


def _pending_total(db: Session, employee_id: int) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(PettyExpense.amount), 0)).where(
            PettyExpense.employee_id == employee_id, PettyExpense.status.in_(OPEN)
        )
    ) or Decimal("0")


def _driver_out(db: Session, rows: list[PettyExpense]) -> list[dict]:
    types = _type_names(db, {r.type_id for r in rows})
    return [
        {
            "id": str(r.public_id),
            "amount": r.amount,
            "category": types.get(r.type_id),
            "invoice_date": r.invoice_date,
            "vendor": r.vendor,
            "note": r.note,
            "status": r.status,
            "decision_note": r.decision_note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def _movements(db: Session, employee_id: int, linked: set[int]) -> list[dict]:
    """His custody's posted movements, the last 30: funded, returned, spent through an expense the office entered
    (what he spent from the app is listed as his requests, not twice)."""
    acc = db.scalar(select(Account.id).where(Account.kind == "petty", Account.employee_id == employee_id))
    if acc is None:
        return []
    rows = db.execute(
        select(
            Journal.public_id,
            Journal.kind,
            Journal.business_date,
            Journal.created_at,
            Journal.reason,
            Journal.source_type,
            Journal.source_id,
            JournalLine.amount,
        )  # fmt: skip
        .join(JournalLine, JournalLine.journal_id == Journal.id)
        .where(JournalLine.account_id == acc, Journal.status == "posted")
        .order_by(Journal.created_at.desc(), Journal.id.desc())
        .limit(60)
    ).all()
    out = []
    for r in rows:
        if r.source_type == "expense" and r.source_id in linked:
            continue
        out.append(
            {
                "id": str(r.public_id),
                "kind": r.kind,
                "amount": r.amount,
                "date": r.business_date,
                "created_at": r.created_at,
                "note": r.reason,
            }
        )
    return out[:30]


# ------------------------------------------------------------------ the holder


def driver_view(db: Session, employee_id: int) -> dict:
    """Whether he holds a custody, its balance and what he can still spend, the expense types he may spend on, his
    custody's movements and his last spending requests."""
    has = cash.is_petty_holder(db, employee_id)
    balance = cash.petty_balance(db, employee_id)
    pending = _pending_total(db, employee_id)
    rows = list(
        db.scalars(
            select(PettyExpense)
            .where(PettyExpense.employee_id == employee_id)
            .order_by(PettyExpense.created_at.desc(), PettyExpense.id.desc())
            .limit(30)
        )
    )
    linked = set(
        db.scalars(
            select(PettyExpense.expense_id).where(
                PettyExpense.employee_id == employee_id, PettyExpense.expense_id.is_not(None)
            )
        )
    )
    return {
        "has_custody": has,
        "balance": balance,
        "pending": Decimal(pending).quantize(cash.FILS),
        "available": max(balance - Decimal(pending), cash.ZERO).quantize(cash.FILS),
        "categories": [{"id": t.id, "code": t.code, "name": t.name} for t in _types(db)] if has else [],
        "movements": _movements(db, employee_id, linked),
        "expenses": _driver_out(db, rows),
    }


def _check_invoice(db: Session, sha: str, device_id: int) -> None:
    """A photo this phone took with its camera (as a fuel receipt), never used for another spending."""
    info = files.get(db, sha)
    if info.content_type not in files.IMAGES:
        raise AppError(422, "photo_must_be_image")
    if info.uploaded_by_device != device_id or info.source != "camera":
        raise AppError(422, "file_not_yours")
    if db.scalar(select(PettyExpense.id).where(PettyExpense.invoice_sha256 == sha)):
        raise AppError(409, "petty_invoice_used")


def driver_spend(db: Session, *, employee_id: int, device_id: int, data: dict) -> dict:
    if db.scalar(select(PettyExpense.id).where(PettyExpense.client_ref == data["client_ref"])):
        raise AppError(409, "petty_expense_exists")  # a resend: already recorded
    driver = people.ref(db, employee_id)
    if not cash.is_petty_holder(db, employee_id):
        raise AppError(409, "petty_no_custody")
    day: date = data.get("invoice_date") or today()
    if day > today():
        raise AppError(422, "petty_invoice_future")
    if day < today() - OLDEST:
        raise AppError(422, "petty_invoice_too_old", days=OLDEST.days)
    if data["type_id"] not in {t.id for t in _types(db)}:
        raise AppError(422, "petty_category_unknown")
    cash.lock_branches(db, petty=[employee_id])  # two requests at once do not both pass the balance
    available = cash.petty_balance(db, employee_id) - Decimal(_pending_total(db, employee_id))
    if data["amount"] > available:
        raise AppError(422, "petty_over_balance", available=f"{max(available, cash.ZERO):.3f}")
    _check_invoice(db, data["invoice_sha256"], device_id)
    row = PettyExpense(
        employee_id=employee_id,
        company_id=driver.company_id,
        branch_id=driver.branch_id,
        client_ref=data["client_ref"],
        type_id=data["type_id"],
        amount=data["amount"],
        invoice_date=day,
        vendor=data.get("vendor") or None,
        note=data.get("note") or None,
        invoice_sha256=data["invoice_sha256"],
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        code = ERRORS.get(violated_constraint(exc) or "")
        if code:
            raise AppError(409, code) from None
        raise
    db.refresh(row)
    notifications.raise_alert(
        db,
        "petty_expense",
        company_id=row.company_id,
        entity_type="petty_expense",
        entity_id=row.public_id,
        params={"name": driver.name, "amount": f"{row.amount:.3f}"},
        dedupe_key=_alert_key(row),
    )
    audit.record(
        db,
        action="cash.petty_spent",
        entity_type="petty_expense",
        entity_id=row.public_id,
        actor_type="device",
        company_id=row.company_id,
        after={"driver": str(driver.public_id), "amount": row.amount, "invoice_date": day.isoformat()},
    )
    db.commit()
    return _driver_out(db, [row])[0]


def driver_cancel(db: Session, *, employee_id: int, public_id) -> dict:
    row = db.scalar(
        select(PettyExpense)
        .where(PettyExpense.public_id == public_id, PettyExpense.employee_id == employee_id)
        .with_for_update()
    )
    if row is None:
        raise AppError(404, "petty_expense_not_found")
    _decided(db, row, status="cancelled")
    notifications.resolve(db, _alert_key(row))
    audit.record(
        db,
        action="cash.petty_cancelled",
        entity_type="petty_expense",
        entity_id=row.public_id,
        actor_type="device",
        company_id=row.company_id,
    )
    db.commit()
    db.refresh(row)
    return _driver_out(db, [row])[0]


def _alert_key(row: PettyExpense) -> str:
    return f"petty_expense:{row.id}"


def _decided(db: Session, row: PettyExpense, **values) -> None:
    """Conditional on pending: a request is decided (or cancelled) once, whoever comes second is told so."""
    done = db.execute(
        update(PettyExpense).where(PettyExpense.id == row.id, PettyExpense.status == "pending").values(**values)
    ).rowcount
    if done != 1:
        raise AppError(409, "petty_expense_decided", status=row.status)


# ------------------------------------------------------------------ the office (all companies: a custody is not a
# company's)


def _office_out(db: Session, rows: list[PettyExpense]) -> list[dict]:
    from app.modules.finance.models import Expense

    types = _type_names(db, {r.type_id for r in rows})
    refs = {e: people.ref(db, e) for e in {r.employee_id for r in rows}}
    deciders = identity.user_names(db, {r.decided_by for r in rows if r.decided_by})
    expenses = dict(
        db.execute(
            select(Expense.id, Expense.public_id).where(Expense.id.in_([r.expense_id for r in rows if r.expense_id]))
        ).all()
    )
    balances = {e: cash.petty_balance(db, e) for e in refs}
    out = []
    for r in rows:
        ref = refs[r.employee_id]
        out.append(
            {
                "id": str(r.public_id),
                "driver": {"id": str(ref.public_id), "name": ref.name},
                "company_id": r.company_id,
                "branch_id": r.branch_id,
                "amount": r.amount,
                "category": types.get(r.type_id),
                "invoice_date": r.invoice_date,
                "vendor": r.vendor,
                "note": r.note,
                "status": r.status,
                "decision_note": r.decision_note,
                "decided_by": deciders.get(r.decided_by),
                "decided_at": r.decided_at,
                "balance": balances[r.employee_id],
                "expense_id": str(expenses[r.expense_id]) if r.expense_id else None,
                "invoice_url": f"/api/v1/cash/petty-expenses/{r.public_id}/invoice",
                "created_at": r.created_at,
            }
        )
    return out


def list_requests(
    db: Session, *, status: str | None = None, employee_id: int | None = None, limit: int = 200
) -> list[dict]:
    q = select(PettyExpense)
    if status:
        q = q.where(PettyExpense.status.in_(status.split(",")))
    if employee_id:
        q = q.where(PettyExpense.employee_id == employee_id)
    q = q.order_by(PettyExpense.created_at.desc(), PettyExpense.id.desc()).limit(min(limit, 500))
    return _office_out(db, list(db.scalars(q)))


def pending_by_holder(db: Session) -> dict[int, tuple[int, Decimal]]:
    """Per holder (employee id): how many spending requests wait for the office, and their total."""
    rows = db.execute(
        select(PettyExpense.employee_id, func.count(), func.sum(PettyExpense.amount))
        .where(PettyExpense.status.in_(OPEN))
        .group_by(PettyExpense.employee_id)
    ).all()
    return {e: (n, Decimal(t)) for e, n, t in rows}


def pending_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(PettyExpense).where(PettyExpense.status.in_(OPEN)))


def _get(db: Session, public_id, *, lock: bool = False) -> PettyExpense:
    q = select(PettyExpense).where(PettyExpense.public_id == public_id)
    row = db.scalar(q.with_for_update() if lock else q)
    if row is None:
        raise AppError(404, "petty_expense_not_found")
    return row


def invoice(db: Session, public_id) -> files.FileInfo:
    return files.get(db, _get(db, public_id).invoice_sha256)


def approve(db: Session, public_id, *, note: str | None, actor_user_id: int) -> dict:
    """The finance expense paid from his custody, created and decided now: the custody goes down by the existing
    posting (refused when he no longer holds enough). With an approval workflow on expenses, the request is in
    review until the expense's last step."""
    from app.modules.finance import service as finance

    row = _get(db, public_id, lock=True)
    if row.status != "pending":
        raise AppError(409, "petty_expense_decided", status=row.status)
    driver = people.ref(db, row.employee_id)
    expense = finance.create_expense(
        db,
        {
            "company_id": row.company_id,
            "branch_id": row.branch_id,
            "type_id": row.type_id,
            "expense_date": row.invoice_date,
            "amount": row.amount,
            "payment_method": "petty",
            "petty_employee_id": driver.public_id,
            "supplier": row.vendor,
            "employee_id": driver.public_id,
            "notes": row.note,
            "files": [row.invoice_sha256],
        },
        actor_user_id=actor_user_id,
        all_companies=True,
        company_ids=[],
        commit=False,
    )
    from app.modules.finance.models import Expense

    expense_id = db.scalar(select(Expense.id).where(Expense.public_id == expense["id"]))
    _decided(db, row, status="in_review", decided_by=actor_user_id, decided_at=utcnow(), expense_id=expense_id)
    notifications.resolve(db, _alert_key(row))
    audit.record(
        db,
        action="cash.petty_approved",
        entity_type="petty_expense",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        company_id=row.company_id,
        after={"amount": row.amount, "expense": expense["id"]},
        comment=note,
    )
    # the expense's decision (its approval workflow's first step when there is one) follows it: expense_changed
    finance.decide_expense(
        db, expense["id"], approve=True, note=note, actor_user_id=actor_user_id, commit=False, all_companies=True,
        company_ids=[],
    )  # fmt: skip
    db.commit()
    db.refresh(row)
    return _office_out(db, [row])[0]


def reject(db: Session, public_id, *, reason: str, actor_user_id: int) -> dict:
    row = _get(db, public_id, lock=True)
    if row.status != "pending":
        raise AppError(409, "petty_expense_decided", status=row.status)
    _decided(db, row, status="rejected", decision_note=reason, decided_by=actor_user_id, decided_at=utcnow())
    notifications.resolve(db, _alert_key(row))
    _notify(db, row, "petty_rejected", reason=reason)
    audit.record(
        db,
        action="cash.petty_rejected",
        entity_type="petty_expense",
        entity_id=row.public_id,
        actor_user_id=actor_user_id,
        company_id=row.company_id,
        comment=reason,
    )
    db.commit()
    db.refresh(row)
    return _office_out(db, [row])[0]


def _notify(db: Session, row: PettyExpense, kind: str, **params) -> None:
    notifications.notify_driver(
        db,
        row.employee_id,
        kind,
        params={"amount": f"{row.amount:.3f}", **params},
        entity_type="petty_expense",
        entity_id=row.public_id,
        dedupe_key=f"{kind}:{row.id}",
    )


def expense_changed(db: Session, expense) -> None:
    """In the caller's transaction: the request behind a petty expense follows it (its last approval step, a
    workflow's refusal, a cancellation that put the money back in the custody)."""
    row = db.scalar(
        select(PettyExpense)
        .where(PettyExpense.expense_id == expense.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        return
    if expense.status == "approved" and row.status != "approved":
        row.status = "approved"
        _notify(db, row, "petty_approved")
    elif expense.status in ("rejected", "cancelled") and row.status != "rejected":
        row.status = "rejected"
        row.decision_note = (expense.decision_note if expense.status == "rejected" else expense.cancel_reason) or "-"
        row.decided_at = row.decided_at or utcnow()
        _notify(db, row, "petty_rejected", reason=row.decision_note)
    db.flush()
