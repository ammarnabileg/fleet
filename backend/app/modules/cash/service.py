"""The cash ledger (spec section 8): double entry, append-only, every rule also enforced by the database.

Accounts: one per driver (positive balance = cash the driver holds for the company), and per branch a treasury,
a bank and the counterpart of what the drivers collect from customers (cod_clearing); plus adjustments, payroll
recovery, write-off and opening balances. A balance is always the sum of its lines; nothing stores a balance.

Events (spec 8.2): a daily report with cash creates a pending collection (driver +X, counterpart -X), shown as the
"unapproved" balance; approval posts it, a correction adds a posted adjustment with its reason; a rejection
rejects it and frees the report for a new one. A receipt at the cashier is a posted deposit (treasury +Y,
driver -Y) with a number unique per branch. A posted journal is never changed: a reversal (once, with a reason)
or an adjustment corrects it.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.cash.models import Account, Journal, JournalLine, Receipt
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

ZERO = Decimal("0.000")
FILS = Decimal("0.001")


@dataclass(frozen=True)
class Balance:
    posted: Decimal
    pending: Decimal

    @property
    def total(self) -> Decimal:
        return self.posted + self.pending


# ------------------------------------------------------------------ accounts and journals


def account(db: Session, kind: str, *, driver_id: int | None = None, branch_id: int | None = None) -> int:
    db.execute(insert(Account).values(kind=kind, driver_id=driver_id, branch_id=branch_id).on_conflict_do_nothing())
    q = select(Account.id).where(Account.kind == kind)
    q = q.where(Account.driver_id == driver_id) if driver_id else q.where(Account.driver_id.is_(None))
    q = q.where(Account.branch_id == branch_id) if branch_id else q.where(Account.branch_id.is_(None))
    return db.scalar(q)


def _journal(
    db: Session,
    kind: str,
    *,
    source_type: str,
    source_id: int,
    lines: list[tuple[int, Decimal]],
    actor_user_id: int | None = None,
    actor_device_id: int | None = None,
    reason: str | None = None,
    reverses_id: int | None = None,
    post: bool = False,
    business_date: date | None = None,
) -> Journal:
    closed = db.scalar(
        select(func.count())
        .select_from(Account)
        .where(Account.id.in_([a for a, _ in lines]), Account.closed_at.is_not(None))
    )
    if closed:
        raise AppError(409, "account_closed")
    journal = Journal(
        kind=kind,
        business_date=business_date or today(),
        source_type=source_type,
        source_id=source_id,
        reason=reason,
        reverses_id=reverses_id,
        created_by=actor_user_id,
        created_by_device=actor_device_id,
    )
    try:
        with db.begin_nested():
            db.add(journal)
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) in ("journals_one_per_source", "journals_one_reversal"):
            raise AppError(409, "journal_exists") from None
        raise
    db.add_all([JournalLine(journal_id=journal.id, account_id=a, amount=m) for a, m in lines if m])
    db.flush()
    if post:
        _decide(db, journal.id, "posted", actor_user_id)
    return journal


def _decide(db: Session, journal_id: int, status: str, actor_user_id: int | None) -> bool:
    """Conditional on pending: deciding twice changes nothing (spec T-LED-03)."""
    return (
        db.execute(
            update(Journal)
            .where(Journal.id == journal_id, Journal.status == "pending")
            .values(status=status, decided_by=actor_user_id, decided_at=func.now())
        ).rowcount
        == 1
    )


def balances(db: Session, account_ids: Iterable[int]) -> dict[int, Balance]:
    ids = list(account_ids)
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT account_id, posted, pending FROM cash.balances WHERE account_id = ANY(:ids)"), {"ids": ids}
    )
    # the view's coalesce(…, 0) has no scale: 0 would reach the screens as "0" instead of "0.000"
    return {a: Balance(Decimal(p).quantize(FILS), Decimal(q).quantize(FILS)) for a, p, q in rows}


def driver_balance(db: Session, employee_id: int) -> Balance:
    acc = db.scalar(select(Account.id).where(Account.kind == "driver", Account.driver_id == employee_id))
    return balances(db, [acc]).get(acc, Balance(ZERO, ZERO)) if acc else Balance(ZERO, ZERO)


def check_balance_alert(db: Session, driver: people.EmployeeRef) -> None:
    """Above the configured limit: an alert, never a block (BRD); it closes itself when the balance comes down."""
    limit = org.get_section(db, "cash").driver_balance_alert
    total = driver_balance(db, driver.id).total
    key = f"cash_balance_high:{driver.id}"
    if total > limit:
        notifications.raise_alert(
            db,
            "cash_balance_high",
            company_id=driver.company_id,
            entity_type="employee",
            entity_id=driver.public_id,
            params={"driver": driver.name, "balance": f"{total:.3f}", "limit": f"{limit:.3f}"},
            dedupe_key=key,
            refresh=True,
        )
    else:
        notifications.resolve(db, key)


# ------------------------------------------------------------------ daily report collections


def _collection(db: Session, report_id: int) -> Journal | None:
    return db.scalar(
        select(Journal).where(
            Journal.source_type == "daily_report",
            Journal.source_id == report_id,
            Journal.kind == "collection",
            Journal.status != "rejected",
        )
    )


def submit_collection(
    db: Session, driver: people.EmployeeRef, *, report_id: int, amount: Decimal, business_date: date, device_id: int
) -> None:
    """In the caller's transaction: pending until the report is reviewed."""
    if amount <= 0:
        return
    drv = account(db, "driver", driver_id=driver.id)
    cod = account(db, "cod_clearing", branch_id=driver.branch_id)
    _journal(
        db,
        "collection",
        source_type="daily_report",
        source_id=report_id,
        lines=[(drv, amount), (cod, -amount)],
        actor_device_id=device_id,
        business_date=business_date,
    )


def approve_collection(
    db: Session,
    driver: people.EmployeeRef,
    *,
    report_id: int,
    reported: Decimal,
    approved: Decimal,
    reason: str | None,
    business_date: date,
    actor_user_id: int,
) -> None:
    """Posts the collection; a corrected amount adds a posted adjustment with the reason (spec T-LED-02)."""
    drv = account(db, "driver", driver_id=driver.id)
    cod = account(db, "cod_clearing", branch_id=driver.branch_id)
    journal = _collection(db, report_id)
    if journal is not None:
        _decide(db, journal.id, "posted", actor_user_id)
    elif approved > 0:  # reported zero, the reviewer counted cash: the collection is the reviewer's figure
        _journal(
            db,
            "collection",
            source_type="daily_report",
            source_id=report_id,
            lines=[(drv, approved), (cod, -approved)],
            actor_user_id=actor_user_id,
            post=True,
            business_date=business_date,
        )
        return
    difference = approved - reported
    if difference:
        _journal(
            db,
            "adjustment",
            source_type="daily_report",
            source_id=report_id,
            lines=[(drv, difference), (cod, -difference)],
            actor_user_id=actor_user_id,
            reason=reason,
            post=True,
            business_date=business_date,
        )


def reject_collection(db: Session, *, report_id: int, actor_user_id: int) -> None:
    journal = _collection(db, report_id)
    if journal is not None:
        _decide(db, journal.id, "rejected", actor_user_id)


# ------------------------------------------------------------------ receipts, treasury, corrections


def _next_receipt_no(db: Session, branch_id: int) -> int:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('cash.receipt:' || :b, 0))"), {"b": branch_id})
    return (db.scalar(select(func.max(Receipt.receipt_no)).where(Receipt.branch_id == branch_id)) or 0) + 1


def _receipt_out(r: Receipt) -> dict:
    return {
        "id": str(r.public_id),
        "receipt_no": r.receipt_no,
        "branch_id": r.branch_id,
        "amount": r.amount,
        "created_at": r.created_at,
        "driver_confirmed_at": r.driver_confirmed_at,
    }


def record_receipt(db: Session, driver: people.EmployeeRef, *, amount: Decimal, actor_user_id: int) -> dict:
    """The driver hands cash to the cashier: a numbered receipt and a posted deposit (spec T-LED-07)."""
    if amount <= 0:
        raise AppError(422, "amount_must_be_positive")
    receipt = Receipt(
        branch_id=driver.branch_id,
        receipt_no=_next_receipt_no(db, driver.branch_id),
        driver_id=driver.id,
        amount=amount,
        created_by=actor_user_id,
    )
    db.add(receipt)
    db.flush()
    db.refresh(receipt)
    drv = account(db, "driver", driver_id=driver.id)
    treasury = account(db, "treasury", branch_id=driver.branch_id)
    _journal(
        db,
        "deposit",
        source_type="receipt",
        source_id=receipt.id,
        lines=[(treasury, amount), (drv, -amount)],
        actor_user_id=actor_user_id,
        post=True,
    )
    check_balance_alert(db, driver)
    out = _receipt_out(receipt)
    audit.record(
        db,
        action="cash.receipt",
        entity_type="receipt",
        entity_id=receipt.public_id,
        actor_user_id=actor_user_id,
        company_id=driver.company_id,
        after={"receipt_no": receipt.receipt_no, "driver": str(driver.public_id), "amount": amount},
    )
    emit(
        db,
        "cash.deposit.posted",
        receipt.public_id,
        {"driver_id": str(driver.public_id), "amount": str(amount), "receipt_no": receipt.receipt_no},
    )
    db.commit()
    return out


def confirm_receipt(db: Session, employee_id: int, public_id) -> dict:
    receipt = db.scalar(select(Receipt).where(Receipt.public_id == public_id, Receipt.driver_id == employee_id))
    if receipt is None:
        raise AppError(404, "receipt_not_found")
    if receipt.driver_confirmed_at is None:
        receipt.driver_confirmed_at = utcnow()
        db.commit()
    return _receipt_out(receipt)


def adjust(db: Session, driver: people.EmployeeRef, *, amount: Decimal, reason: str, actor_user_id: int) -> dict:
    """A manual correction of a driver's balance (+ the driver owes more, - less), always with its reason."""
    if not amount:
        raise AppError(422, "amount_must_not_be_zero")
    drv = account(db, "driver", driver_id=driver.id)
    adj = account(db, "adjustments")
    journal = _journal(
        db,
        "adjustment",
        source_type="manual",
        source_id=driver.id,
        lines=[(drv, amount), (adj, -amount)],
        actor_user_id=actor_user_id,
        reason=reason,
        post=True,
    )
    check_balance_alert(db, driver)
    audit.record(
        db,
        action="cash.adjustment",
        entity_type="journal",
        entity_id=journal.public_id,
        actor_user_id=actor_user_id,
        company_id=driver.company_id,
        after={"driver": str(driver.public_id), "amount": amount, "reason": reason},
    )
    db.commit()
    return journal_out(db, journal)


def reverse(db: Session, public_id, *, reason: str, actor_user_id: int, all_companies: bool, company_ids) -> dict:
    """Undo a posted journal with the opposite lines; at most once (spec T-LED-11)."""
    original = db.scalar(select(Journal).where(Journal.public_id == public_id))
    if original is None or not _visible(db, original.id, all_companies, company_ids):
        raise AppError(404, "journal_not_found")
    if original.status != "posted" or original.kind == "reversal":
        raise AppError(409, "journal_not_reversible")
    lines = db.execute(select(JournalLine.account_id, JournalLine.amount).where(JournalLine.journal_id == original.id))
    journal = _journal(
        db,
        "reversal",
        source_type=original.source_type,
        source_id=original.source_id,
        lines=[(a, -m) for a, m in lines],
        actor_user_id=actor_user_id,
        reason=reason,
        reverses_id=original.id,
        post=True,
    )
    audit.record(
        db,
        action="cash.reversal",
        entity_type="journal",
        entity_id=journal.public_id,
        actor_user_id=actor_user_id,
        after={"reverses": str(original.public_id), "reason": reason},
    )
    for employee_id in _drivers_of(db, journal.id):
        check_balance_alert(db, people.ref(db, employee_id))
    db.commit()
    return journal_out(db, journal)


def bank_deposit(db: Session, *, branch_id: int, amount: Decimal, reference: str, actor_user_id: int) -> dict:
    """Treasury cash taken to the bank (bank +Z, treasury -Z)."""
    if amount <= 0:
        raise AppError(422, "amount_must_be_positive")
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")
    treasury = account(db, "treasury", branch_id=branch_id)
    if balances(db, [treasury]).get(treasury, Balance(ZERO, ZERO)).posted < amount:
        raise AppError(422, "treasury_insufficient")
    bank = account(db, "bank", branch_id=branch_id)
    journal = _journal(
        db,
        "bank_deposit",
        source_type="bank_deposit",
        source_id=branch_id,
        lines=[(bank, amount), (treasury, -amount)],
        actor_user_id=actor_user_id,
        reason=reference,
        post=True,
    )
    audit.record(
        db,
        action="cash.bank_deposit",
        entity_type="journal",
        entity_id=journal.public_id,
        actor_user_id=actor_user_id,
        after={"branch_id": branch_id, "amount": amount, "reference": reference},
    )
    db.commit()
    return journal_out(db, journal)


# ------------------------------------------------------------------ end of service (spec 8.4)


def flag_departed(db: Session, driver: people.EmployeeRef) -> None:
    """Employment ended while the driver still holds (or is owed) cash: someone must settle it."""
    balance = driver_balance(db, driver.id)
    if balance.posted or balance.pending:
        notifications.raise_alert(
            db,
            "driver_left_with_cash",
            company_id=driver.company_id,
            entity_type="employee",
            entity_id=driver.public_id,
            params={"driver": driver.name, "balance": f"{balance.total:.3f}"},
            dedupe_key=f"driver_left_with_cash:{driver.id}",
            refresh=True,
        )
        db.commit()


def settle(
    db: Session,
    driver: people.EmployeeRef,
    *,
    payroll_amount: Decimal,
    writeoff_amount: Decimal,
    reason: str | None,
    actor_user_id: int,
) -> dict:
    """Brings the account of a driver whose employment ended to exactly zero, then closes it: what he owes is
    recovered through payroll and/or written off (with a reason); what the company owes him is paid from the
    treasury of his branch. Every pending journal must be decided first."""
    if not driver.is_terminal:
        raise AppError(409, "settlement_needs_end_of_service")
    acc = account(db, "driver", driver_id=driver.id)
    pending = db.scalar(
        select(func.count())
        .select_from(Journal)
        .join(JournalLine, JournalLine.journal_id == Journal.id)
        .where(JournalLine.account_id == acc, Journal.status == "pending")
    )
    if pending:
        raise AppError(409, "pending_journals_exist", count=pending)
    balance = driver_balance(db, driver.id).posted
    if balance > 0 and payroll_amount + writeoff_amount != balance:
        raise AppError(422, "settlement_must_zero", balance=f"{balance:.3f}")
    if balance <= 0 and (payroll_amount or writeoff_amount):
        raise AppError(422, "settlement_must_zero", balance=f"{balance:.3f}")
    if writeoff_amount and not reason:
        raise AppError(422, "reason_required")
    journals = []
    if payroll_amount:
        journals.append(
            _journal(
                db,
                "settlement",
                source_type="settlement",
                source_id=driver.id,
                lines=[(account(db, "payroll_recovery"), payroll_amount), (acc, -payroll_amount)],
                actor_user_id=actor_user_id,
                reason=reason,
                post=True,
            )
        )
    if writeoff_amount:
        journals.append(
            _journal(
                db,
                "writeoff",
                source_type="settlement",
                source_id=driver.id,
                lines=[(account(db, "writeoff"), writeoff_amount), (acc, -writeoff_amount)],
                actor_user_id=actor_user_id,
                reason=reason,
                post=True,
            )
        )
    if balance < 0:  # the company owes the driver: paid out of his branch's treasury
        treasury = account(db, "treasury", branch_id=driver.branch_id)
        journals.append(
            _journal(
                db,
                "settlement",
                source_type="settlement",
                source_id=driver.id,
                lines=[(acc, -balance), (treasury, balance)],
                actor_user_id=actor_user_id,
                reason=reason,
                post=True,
            )
        )
    db.execute(update(Account).where(Account.id == acc).values(closed_at=func.now()))
    notifications.resolve(db, f"driver_left_with_cash:{driver.id}")
    notifications.resolve(db, f"cash_balance_high:{driver.id}")
    audit.record(
        db,
        action="cash.settlement",
        entity_type="employee",
        entity_id=driver.public_id,
        actor_user_id=actor_user_id,
        company_id=driver.company_id,
        after={"balance": balance, "payroll": payroll_amount, "writeoff": writeoff_amount, "reason": reason},
    )
    emit(
        db,
        "cash.settlement.posted",
        driver.public_id,
        {  # payroll deducts payroll_amount from the final pay
            "employee_id": str(driver.public_id),
            "payroll_amount": f"{payroll_amount:.3f}",
            "writeoff_amount": f"{writeoff_amount:.3f}",
            "paid_out": f"{-balance if balance < 0 else ZERO:.3f}",
        },
    )
    db.commit()
    return statement(db, driver) | {"closed": True}


def opening_balance(
    db: Session,
    driver: people.EmployeeRef,
    *,
    amount: Decimal,
    business_date: date,
    approved_by: str,
    actor_user_id: int,
) -> bool:
    """The cash a driver holds on go-live day, approved by the accountant (onboarding workbook), in the caller's
    transaction. Once per driver: the same amount again is skipped; a different one is an error (adjust instead)."""
    existing = db.scalar(
        select(Journal).where(
            Journal.source_type == "import",
            Journal.source_id == driver.id,
            Journal.kind == "opening",
            Journal.status != "rejected",
        )
    )
    if existing is not None:
        current = db.scalar(
            select(JournalLine.amount)
            .join(Account, Account.id == JournalLine.account_id)
            .where(JournalLine.journal_id == existing.id, Account.kind == "driver")
        )
        if current == amount:
            return False
        raise AppError(409, "opening_balance_exists")
    if not amount:
        return False
    _journal(
        db,
        "opening",
        source_type="import",
        source_id=driver.id,
        lines=[(account(db, "driver", driver_id=driver.id), amount), (account(db, "opening"), -amount)],
        actor_user_id=actor_user_id,
        reason=f"approved by {approved_by}",
        post=True,
        business_date=business_date,
    )
    return True


# ------------------------------------------------------------------ reading


def _drivers_of(db: Session, journal_id: int) -> list[int]:
    q = (
        select(Account.driver_id)
        .join(JournalLine, JournalLine.account_id == Account.id)
        .where(JournalLine.journal_id == journal_id, Account.kind == "driver")
    )
    return list(db.scalars(q))


def _visible(db: Session, journal_id: int, all_companies: bool, company_ids) -> bool:
    """A company-limited user sees the journals of drivers in their companies (treasury journals: all-company users)."""
    if all_companies:
        return True
    drivers = _drivers_of(db, journal_id)
    scope = set(company_ids)
    return bool(drivers) and all((ref := people.ref(db, d)) and ref.company_id in scope for d in drivers)


def journal_out(db: Session, j: Journal) -> dict:
    lines = db.execute(
        select(Account.kind, Account.driver_id, Account.branch_id, JournalLine.amount)
        .join(Account, Account.id == JournalLine.account_id)
        .where(JournalLine.journal_id == j.id)
    )
    db.refresh(j)
    return {
        "id": str(j.public_id),
        "kind": j.kind,
        "status": j.status,
        "business_date": j.business_date,
        "source_type": j.source_type,
        "reason": j.reason,
        "created_at": j.created_at,
        "decided_at": j.decided_at,
        "lines": [{"account": k, "branch_id": b, "driver": d is not None, "amount": a} for k, d, b, a in lines],
    }


def statement(db: Session, driver: people.EmployeeRef, *, limit: int = 100) -> dict:
    """A driver's account, newest first, with the running posted balance."""
    acc = db.scalar(select(Account.id).where(Account.kind == "driver", Account.driver_id == driver.id))
    balance = driver_balance(db, driver.id)
    if acc is None:
        return {"posted": ZERO, "pending": ZERO, "total": ZERO, "lines": []}
    rows = db.execute(
        select(Journal, JournalLine.amount)
        .join(JournalLine, JournalLine.journal_id == Journal.id)
        .where(JournalLine.account_id == acc)
        .order_by(Journal.id.desc())
        .limit(min(limit, 500))
    ).all()
    return {
        "posted": balance.posted,
        "pending": balance.pending,
        "total": balance.total,
        "lines": [
            {
                "journal_id": str(j.public_id),
                "kind": j.kind,
                "status": j.status,
                "amount": amount,
                "business_date": j.business_date,
                "reason": j.reason,
                "source_type": j.source_type,
                "created_at": j.created_at,
            }
            for j, amount in rows
        ],
    }


def driver_balances(db: Session, drivers: list[people.EmployeeRef]) -> list[dict]:
    accounts = (
        dict(
            db.execute(
                select(Account.driver_id, Account.id).where(
                    Account.kind == "driver", Account.driver_id.in_([d.id for d in drivers])
                )
            ).all()
        )
        if drivers
        else {}
    )
    found = balances(db, accounts.values())
    limit = org.get_section(db, "cash").driver_balance_alert
    out = []
    for d in drivers:
        b = found.get(accounts.get(d.id), Balance(ZERO, ZERO))
        if b.posted or b.pending:
            out.append(
                {
                    "driver": {"id": str(d.public_id), "name": d.name},
                    "company_id": d.company_id,
                    "posted": b.posted,
                    "pending": b.pending,
                    "total": b.total,
                    "over_limit": b.total > limit,
                }
            )
    return sorted(out, key=lambda x: x["total"], reverse=True)


def receipts_for_driver(db: Session, employee_id: int, limit: int = 20) -> list[dict]:
    q = select(Receipt).where(Receipt.driver_id == employee_id).order_by(Receipt.id.desc()).limit(limit)
    return [_receipt_out(r) for r in db.scalars(q)]


def treasury(db: Session) -> list[dict]:
    branches = org.list_branches(db)
    ids = {
        (k, b["id"]): account(db, k, branch_id=b["id"]) for b in branches for k in ("treasury", "bank", "cod_clearing")
    }
    found = balances(db, ids.values())
    db.commit()
    return [
        {
            "branch": b,
            **{
                k: found.get(ids[(k, b["id"])], Balance(ZERO, ZERO)).posted
                for k in ("treasury", "bank", "cod_clearing")
            },
        }
        for b in branches
    ]


# ------------------------------------------------------------------ invariants (nightly)


def check_invariants(db: Session) -> list[str]:
    """Spec 8.5: all posted lines sum to zero; no pending journal older than the review limit."""
    problems = []
    total = db.scalar(
        text(
            "SELECT coalesce(sum(l.amount), 0) FROM cash.journal_lines l "
            "JOIN cash.journals j ON j.id = l.journal_id WHERE j.status = 'posted'"
        )
    )
    if total != 0:
        problems.append(f"posted lines sum to {total}")
    hours = org.get_section(db, "cash").report_review_hours
    stale = db.scalar(
        select(func.count())
        .select_from(Journal)
        .where(
            Journal.status == "pending", Journal.created_at < func.now() - text(f"interval '{int(hours) * 2} hours'")
        )
    )
    if stale:
        problems.append(f"{stale} pending journals older than {hours * 2} hours")
    for problem in problems:
        notifications.raise_alert(
            db,
            "ledger_invariant",
            company_id=None,
            params={"problem": problem},
            dedupe_key=f"ledger_invariant:{problem}",
        )
    db.commit()
    return problems
