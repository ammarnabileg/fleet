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
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.cash.models import Account, Journal, JournalLine, Receipt, TreasuryClosing
from app.modules.files import service as files
from app.modules.i18n import service as i18n
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
    attachment_sha256: str | None = None,
) -> Journal:
    closed = db.scalar(
        select(func.count())
        .select_from(Account)
        .where(Account.id.in_([a for a, _ in lines]), Account.closed_at.is_not(None))
    )
    if closed:
        raise AppError(409, "account_closed")
    business_date = business_date or today()
    _check_day(db, [a for a, _ in lines], business_date)
    journal = Journal(
        kind=kind,
        business_date=business_date,
        source_type=source_type,
        source_id=source_id,
        reason=reason,
        reverses_id=reverses_id,
        created_by=actor_user_id,
        created_by_device=actor_device_id,
        attachment_sha256=attachment_sha256,
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


def _check_day(db: Session, account_ids: list[int], day: date) -> None:
    """A journal on a branch's treasury takes the treasury's lock (a count and close reads its balance under it) and
    is refused when dated on or before the branch's last closed day (the database refuses it too)."""
    branches = sorted(
        set(db.scalars(select(Account.branch_id).where(Account.id.in_(account_ids), Account.kind == "treasury")))
    )
    if not branches:
        return
    lock_branches(db, treasury=branches)
    for b in branches:
        _open_day(db, b, day)


def _open_day(db: Session, branch_id: int, day: date) -> None:
    """Under the treasury's lock: refused when the day is on or before the branch's last closed day."""
    closed = last_closed_day(db, [branch_id])
    if closed is not None and day <= closed:
        raise AppError(409, "treasury_day_closed", day=day.isoformat())


def last_closed_day(db: Session, branch_ids: Iterable[int]) -> date | None:
    """The last day closed by a count (standing, not reopened) among these branches' treasuries."""
    return db.scalar(
        select(func.max(TreasuryClosing.day)).where(
            TreasuryClosing.branch_id.in_(list(branch_ids)), TreasuryClosing.reopened_at.is_(None)
        )
    )


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


def lock_branches(db: Session, *, treasury: Iterable[int] = (), bank: Iterable[int] = ()) -> None:
    """Serializes what reads a treasury's or a bank's balance before moving money out of it, until the transaction
    ends. Always in one order, every treasury (by branch) before every bank, so two never wait on each other."""
    for kind, branch_ids in (("treasury", treasury), ("bank", bank)):
        for b in sorted(set(branch_ids)):
            db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"cash.{kind}:{b}"})


def _posted(db: Session, account_id: int) -> Decimal:
    return balances(db, [account_id]).get(account_id, Balance(ZERO, ZERO)).posted


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


def replace_collection(
    db: Session, driver: people.EmployeeRef, *, report_id: int, amount: Decimal, business_date: date, device_id: int
) -> None:
    """The driver corrected his report's cash before review: the pending collection gives way to the new amount
    (never posted, so nothing to reverse)."""
    journal = _collection(db, report_id)
    if journal is not None and not _decide(db, journal.id, "rejected", None):
        raise AppError(409, "journal_decided")  # already posted: only an approved change may move it now
    db.flush()
    submit_collection(db, driver, report_id=report_id, amount=amount, business_date=business_date, device_id=device_id)


def correct_approved(
    db: Session,
    driver: people.EmployeeRef,
    *,
    report_id: int,
    difference: Decimal,
    reason: str | None,
    business_date: date,
    actor_user_id: int,
) -> None:
    """A change to an approved report's cash, approved by the reviewer: the difference is posted as an adjustment
    with the reason; the collection already posted stays as it was."""
    if not difference:
        return
    drv = account(db, "driver", driver_id=driver.id)
    cod = account(db, "cod_clearing", branch_id=driver.branch_id)
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


UNCONFIRMED_AFTER = timedelta(hours=24)


def _receipt_out(r: Receipt) -> dict:
    return {
        "id": str(r.public_id),
        "receipt_no": r.receipt_no,
        "branch_id": r.branch_id,
        "amount": r.amount,
        "created_at": r.created_at,
        "driver_confirmed_at": r.driver_confirmed_at,
        # still not confirmed by the driver a day later (BRD FR-CSH-05)
        "unconfirmed_late": r.driver_confirmed_at is None and r.created_at < utcnow() - UNCONFIRMED_AFTER,
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
    check_treasury(db, [driver.branch_id])
    notifications.notify_driver(
        db,
        driver.id,
        "receipt_issued",
        params={"number": receipt.receipt_no, "amount": f"{amount:.3f}"},
        entity_type="receipt",
        entity_id=receipt.public_id,
    )
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


def _adjustment_approval(db: Session, journal: Journal, driver: people.EmployeeRef, amount: Decimal) -> dict:
    lang = i18n.default_language(db).code
    return {
        "document_id": journal.id,
        "document_key": journal.public_id,
        "document_ref": f"{i18n.pick(driver.name, lang, lang)} {amount:+.3f}",
        "company_id": driver.company_id,
        "amount": abs(amount),
    }


def adjust(db: Session, driver: people.EmployeeRef, *, amount: Decimal, reason: str, actor_user_id: int) -> dict:
    """A manual correction of a driver's balance (+ the driver owes more, - less), always with its reason. With an
    approval workflow for the amount it waits, pending (the "unapproved" balance), until its last step (FR-CSH-09)."""
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
    )
    approval = _adjustment_approval(db, journal, driver, amount)
    if not approvals.submitted(db, "cash_adjustment", **approval, actor_user_id=actor_user_id):
        _decide(db, journal.id, "posted", actor_user_id)
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


def decide_adjustment(
    db: Session, public_id, *, approve: bool, reason: str | None, actor_user_id: int, all_companies: bool, company_ids
) -> dict:
    """A step of a pending adjustment's workflow, from the approvals inbox: the last approval posts it, a refusal
    (with its reason) rejects it."""
    journal = db.scalar(
        select(Journal).where(Journal.public_id == public_id, Journal.kind == "adjustment").with_for_update()
    )
    if journal is None or not _visible(db, journal.id, all_companies, company_ids):
        raise AppError(404, "journal_not_found")
    if journal.status != "pending":
        raise AppError(409, "journal_decided", status=journal.status)
    driver = people.ref(db, journal.source_id)
    amount = db.scalar(
        select(JournalLine.amount)
        .join(Account, Account.id == JournalLine.account_id)
        .where(JournalLine.journal_id == journal.id, Account.kind == "driver")
    )
    approval = _adjustment_approval(db, journal, driver, amount)
    if approvals.gate(db, "cash_adjustment", **approval, actor_user_id=actor_user_id, approve=approve, reason=reason):
        _decide(db, journal.id, "posted" if approve else "rejected", actor_user_id)
        if approve:
            check_balance_alert(db, driver)
        audit.record(
            db,
            action="cash.adjustment_approved" if approve else "cash.adjustment_rejected",
            entity_type="journal",
            entity_id=journal.public_id,
            actor_user_id=actor_user_id,
            company_id=driver.company_id,
            comment=reason,
        )
    db.commit()
    db.refresh(journal)
    return journal_out(db, journal)


def reverse(db: Session, public_id, *, reason: str, actor_user_id: int, all_companies: bool, company_ids) -> dict:
    """Undo a posted journal with the opposite lines; at most once (spec T-LED-11)."""
    original = db.scalar(select(Journal).where(Journal.public_id == public_id))
    if original is None or not _visible(db, original.id, all_companies, company_ids):
        raise AppError(404, "journal_not_found")
    if original.status != "posted" or original.kind == "reversal":
        raise AppError(409, "journal_not_reversible")
    if original.kind == "disbursement":  # undone with its document (the expense cancelled), never on its own
        raise AppError(409, "disbursement_from_expense")
    if original.kind == "count_diff":  # undone by reopening the day it closed
        raise AppError(409, "count_diff_from_closing")
    lines = list(
        db.execute(
            select(JournalLine.account_id, JournalLine.amount, Account.kind, Account.branch_id)
            .join(Account, Account.id == JournalLine.account_id)
            .where(JournalLine.journal_id == original.id)
        )
    )
    # every treasury and bank it touches locked first, in the one order; one the reversal takes money out of must
    # hold it (as a deposit or a withdrawal would)
    lock_branches(
        db, treasury=[b for *_, k, b in lines if k == "treasury"], bank=[b for *_, k, b in lines if k == "bank"]
    )
    out_of = [(a, m, k, b) for a, m, k, b in lines if k in ("treasury", "bank") and m > 0]
    for a, m, k, _ in out_of:
        if _posted(db, a) < m:
            raise AppError(422, f"{k}_insufficient")
    journal = _journal(
        db,
        "reversal",
        source_type=original.source_type,
        source_id=original.source_id,
        lines=[(a, -m) for a, m, *_ in lines],
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
    check_treasury(db)
    for employee_id in _drivers_of(db, journal.id):
        check_balance_alert(db, people.ref(db, employee_id))
    if original.kind == "fuel":  # the fuel claim it paid waits for a decision again
        from app.modules.cash import fuel

        fuel.reopen(db, original, reason=reason, actor_user_id=actor_user_id)
    db.commit()
    return journal_out(db, journal)


def bank_deposit(
    db: Session, *, branch_id: int, amount: Decimal, reference: str, receipt_sha256: str, actor_user_id: int
) -> dict:
    """Treasury cash taken to the bank (bank +Z, treasury -Z), with the bank's reference and the photo of its
    receipt (BRD FR-CSH-07)."""
    if amount <= 0:
        raise AppError(422, "amount_must_be_positive")
    files.get(db, receipt_sha256)
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")
    treasury = account(db, "treasury", branch_id=branch_id)
    lock_branches(db, treasury=[branch_id], bank=[branch_id])
    _open_day(db, branch_id, today())
    if _posted(db, treasury) < amount:
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
        attachment_sha256=receipt_sha256,
    )
    audit.record(
        db,
        action="cash.bank_deposit",
        entity_type="journal",
        entity_id=journal.public_id,
        actor_user_id=actor_user_id,
        after={"branch_id": branch_id, "amount": amount, "reference": reference, "receipt": receipt_sha256},
    )
    check_treasury(db, [branch_id])
    db.commit()
    return journal_out(db, journal)


def bank_withdrawal(
    db: Session, *, branch_id: int, amount: Decimal, reference: str, attachment_sha256: str, actor_user_id: int
) -> dict:
    """Cash taken from the bank back to a branch treasury (treasury +Z, bank -Z), with the bank's reference and the
    photo of its withdrawal slip."""
    if amount <= 0:
        raise AppError(422, "amount_must_be_positive")
    files.get(db, attachment_sha256)
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")
    bank = account(db, "bank", branch_id=branch_id)
    lock_branches(db, treasury=[branch_id], bank=[branch_id])
    _open_day(db, branch_id, today())
    if _posted(db, bank) < amount:
        raise AppError(422, "bank_insufficient")
    treasury = account(db, "treasury", branch_id=branch_id)
    journal = _journal(
        db,
        "bank_withdrawal",
        source_type="bank_withdrawal",
        source_id=branch_id,
        lines=[(treasury, amount), (bank, -amount)],
        actor_user_id=actor_user_id,
        reason=reference,
        post=True,
        attachment_sha256=attachment_sha256,
    )
    audit.record(
        db,
        action="cash.bank_withdrawal",
        entity_type="journal",
        entity_id=journal.public_id,
        actor_user_id=actor_user_id,
        after={"branch_id": branch_id, "amount": amount, "reference": reference, "slip": attachment_sha256},
    )
    check_treasury(db, [branch_id])
    db.commit()
    return journal_out(db, journal)


# ------------------------------------------------------------------ money paid out of a treasury by another module


def disburse(
    db: Session,
    *,
    branch_id: int,
    amount: Decimal,
    source_type: str,
    source_id: int,
    reason: str,
    actor_user_id: int | None,
    business_date: date | None = None,
    attachment_sha256: str | None = None,
) -> None:
    """In the caller's transaction: money out of a branch treasury for a document of another module (an expense paid
    from it, an advance), posted at once: treasury -X, disbursements +X. Refused when the treasury holds less. One per
    document; it is undone only with its document (undo_disbursement), never reversed on its own. The document's own
    entry already credits the treasury in the books: this journal makes none (finance.posting)."""
    if amount <= 0:
        raise AppError(422, "amount_must_be_positive")
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")
    treasury = account(db, "treasury", branch_id=branch_id)
    lock_branches(db, treasury=[branch_id])
    _open_day(db, branch_id, business_date or today())
    if _posted(db, treasury) < amount:
        raise AppError(422, "treasury_insufficient")
    _journal(
        db,
        "disbursement",
        source_type=source_type,
        source_id=source_id,
        lines=[(treasury, -amount), (account(db, "disbursements"), amount)],
        actor_user_id=actor_user_id,
        reason=reason,
        post=True,
        business_date=business_date,
        attachment_sha256=attachment_sha256,
    )
    check_treasury(db, [branch_id])


def undo_disbursement(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    reason: str,
    actor_user_id: int | None,
    amount: Decimal | None = None,
) -> bool:
    """In the caller's transaction: the document was cancelled, its money is back in the treasury: the disbursement's
    reversal, of all of it or (an advance partly recovered already) of `amount`. Nothing when there is none."""
    original = db.scalar(
        select(Journal).where(
            Journal.source_type == source_type,
            Journal.source_id == source_id,
            Journal.kind == "disbursement",
            Journal.status == "posted",
        )
    )
    if original is None:
        return False
    lines = list(
        db.execute(select(JournalLine.account_id, JournalLine.amount).where(JournalLine.journal_id == original.id))
    )
    full = max(m for _, m in lines)
    back = full if amount is None else min(amount, full)
    if back <= 0:
        return False
    _journal(
        db,
        "reversal",
        source_type=source_type,
        source_id=source_id,
        lines=[(a, -back if m > 0 else back) for a, m in lines],
        actor_user_id=actor_user_id,
        reason=reason,
        reverses_id=original.id,
        post=True,
    )
    check_treasury(db)
    return True


def journal_attachment(db: Session, public_id, *, all_companies: bool, company_ids) -> files.FileInfo:
    """A journal's attachment (a bank receipt, a withdrawal slip, an expense's receipt): a treasury or bank journal
    (no driver in it) for an all-companies user only, a driver's for whoever sees the driver."""
    j = db.scalar(select(Journal).where(Journal.public_id == public_id))
    if j is None or j.attachment_sha256 is None:
        raise AppError(404, "file_not_found")
    if not all_companies and not _visible(db, j.id, all_companies, company_ids):
        raise AppError(403, "company_out_of_scope")
    return files.get(db, j.attachment_sha256)


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
    if balance < 0:
        check_treasury(db, [driver.branch_id])
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
        "has_attachment": j.attachment_sha256 is not None,
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


def unconfirmed_receipts(db: Session, drivers: list[people.EmployeeRef]) -> list[dict]:
    """The receipts these drivers have not confirmed a day after they were given (BRD FR-CSH-05), oldest first."""
    by_id = {d.id: d for d in drivers}
    if not by_id:
        return []
    q = (
        select(Receipt)
        .where(
            Receipt.driver_id.in_(list(by_id)),
            Receipt.driver_confirmed_at.is_(None),
            Receipt.created_at < utcnow() - UNCONFIRMED_AFTER,
        )
        .order_by(Receipt.created_at)
        .limit(500)
    )
    return [
        _receipt_out(r) | {"driver": {"id": str(by_id[r.driver_id].public_id), "name": by_id[r.driver_id].name}}
        for r in db.scalars(q)
    ]


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


def _branch(db: Session, branch_public_id) -> dict:
    branch = next((b for b in org.list_branches(db) if b["public_id"] == str(branch_public_id)), None)
    if branch is None:
        raise AppError(404, "branch_not_found")
    return branch


MOVEMENTS_MAX = 2000
REVERSIBLE_HERE = ("deposit", "bank_deposit", "bank_withdrawal")


def movements(
    db: Session,
    branch_public_id,
    *,
    kind: str,
    date_from: date,
    date_to: date,
    limit: int,
    can_reverse: bool,
    all_companies: bool,
    company_ids,
) -> dict:
    """A branch's treasury (or bank) as it moved: the balance at the start of date_from, every posted journal on it of
    business dates date_from..date_to (oldest first) with the running balance, and the balance at the end. A driver's
    receipt says whose cash it was; a disbursement, its document; a bank deposit or withdrawal, the bank's reference.
    reversible: what this user may reverse from here (a receipt of a driver he sees, a bank deposit or withdrawal by
    an all-companies user); a disbursement never (it goes with its document)."""
    if not all_companies:  # a branch's treasury and bank are shared by all its companies
        raise AppError(403, "company_out_of_scope")
    if date_to < date_from:
        raise AppError(422, "invalid_range")
    branch = _branch(db, branch_public_id)
    acc = account(db, kind, branch_id=branch["id"])
    closed_through = last_closed_day(db, [branch["id"]]) if kind == "treasury" else None
    posted = (
        select(Journal, JournalLine.amount)
        .join(JournalLine, JournalLine.journal_id == Journal.id)
        .where(JournalLine.account_id == acc, Journal.status == "posted")
    )
    opening = db.scalar(
        select(func.coalesce(func.sum(JournalLine.amount), 0))
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(JournalLine.account_id == acc, Journal.status == "posted", Journal.business_date < date_from)
    )
    period_total = db.scalar(
        select(func.coalesce(func.sum(JournalLine.amount), 0))
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            JournalLine.account_id == acc,
            Journal.status == "posted",
            Journal.business_date.between(date_from, date_to),
        )
    )
    rows = db.execute(
        posted.where(Journal.business_date.between(date_from, date_to))
        .order_by(Journal.business_date, Journal.id)
        .limit(min(limit, MOVEMENTS_MAX))
    ).all()
    ids = [j.id for j, _ in rows]
    reversed_ids = set(
        db.scalars(select(Journal.reverses_id).where(Journal.kind == "reversal", Journal.reverses_id.in_(ids)))
    )
    original_kinds = dict(
        db.execute(
            select(Journal.id, Journal.kind).where(Journal.id.in_({j.reverses_id for j, _ in rows if j.reverses_id}))
        ).all()
    )
    receipts = {
        r.id: r
        for r in db.scalars(
            select(Receipt).where(Receipt.id.in_([j.source_id for j, _ in rows if j.source_type == "receipt"]))
        )
    }
    drivers = journal_drivers(db, ids)
    types = {sha: files.get(db, sha).content_type for sha in {j.attachment_sha256 for j, _ in rows} if sha}
    named = people.names(db, set(drivers.values()))
    balance = Decimal(opening).quantize(FILS)
    lines = []
    for j, amount in rows:
        balance += amount
        receipt = receipts.get(j.source_id) if j.source_type == "receipt" else None
        driver = named.get(drivers.get(j.id))
        reversible = (
            can_reverse
            and j.kind in REVERSIBLE_HERE
            and j.id not in reversed_ids
            and (_visible(db, j.id, all_companies, company_ids) if j.kind == "deposit" else all_companies)
        )
        lines.append(
            {
                "journal_id": str(j.public_id),
                "kind": j.kind,
                "reverses_kind": original_kinds.get(j.reverses_id),
                "business_date": j.business_date,
                "created_at": j.created_at,
                "driver": driver,
                "receipt_no": receipt.receipt_no if receipt else None,
                "description": j.reason,
                "amount": amount,
                "balance": balance,
                "has_attachment": j.attachment_sha256 is not None,
                "attachment_type": types.get(j.attachment_sha256),
                "reversed": j.id in reversed_ids,
                "reversible": reversible,
                "closed": closed_through is not None and j.business_date <= closed_through,
            }
        )
    db.commit()  # the account, made on first sight
    return {
        "branch": branch,
        "account": kind,
        "closed_through": closed_through,
        "date_from": date_from,
        "date_to": date_to,
        "opening": Decimal(opening).quantize(FILS),
        "closing": (Decimal(opening) + Decimal(period_total)).quantize(FILS),
        "truncated": len(rows) == min(limit, MOVEMENTS_MAX)
        and len(rows)
        < db.scalar(
            select(func.count()).select_from(posted.where(Journal.business_date.between(date_from, date_to)).subquery())
        ),
        "lines": lines,
    }


# ------------------------------------------------------------------ the treasury's daily count and close

# Kuwaiti dinar notes and coins, as the count names them: {"20": how many, ..., "0.005": how many}
DENOMINATIONS = ("20", "10", "5", "1", "0.5", "0.25", "0.100", "0.050", "0.020", "0.010", "0.005")


def _denominations(raw: dict | None) -> tuple[dict | None, Decimal | None]:
    """The notes and coins counted, under their usual names, and what they add up to (None when not given)."""
    if raw is None:
        return None, None
    names = {Decimal(k): k for k in DENOMINATIONS}
    out: dict[str, int] = {}
    for key, count in raw.items():
        try:
            name = names.get(Decimal(str(key)))
        except ArithmeticError:
            name = None
        if name is None:
            raise AppError(422, "denomination_unknown", value=str(key))
        if count:
            out[name] = out.get(name, 0) + int(count)
    total = sum((Decimal(k) * n for k, n in out.items()), ZERO)
    return {k: out[k] for k in DENOMINATIONS if k in out}, total.quantize(FILS)


def _last_closing(db: Session, branch_id: int) -> TreasuryClosing | None:
    return db.scalar(
        select(TreasuryClosing)
        .where(TreasuryClosing.branch_id == branch_id, TreasuryClosing.reopened_at.is_(None))
        .order_by(TreasuryClosing.day.desc())
        .limit(1)
    )


def _book(db: Session, account_id: int, day: date) -> Decimal:
    """A treasury's posted balance at the end of a day: every posted journal dated up to it."""
    total = db.scalar(
        select(func.coalesce(func.sum(JournalLine.amount), 0))
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(JournalLine.account_id == account_id, Journal.status == "posted", Journal.business_date <= day)
    )
    return Decimal(total).quantize(FILS)


def _moved_days(db: Session, account_id: int, after: date | None, until: date) -> list[date]:
    """The days after `after` up to `until` on which the account moved (posted journals), oldest first."""
    q = (
        select(Journal.business_date)
        .join(JournalLine, JournalLine.journal_id == Journal.id)
        .where(JournalLine.account_id == account_id, Journal.status == "posted", Journal.business_date <= until)
        .distinct()
        .order_by(Journal.business_date)
    )
    if after is not None:
        q = q.where(Journal.business_date > after)
    return list(db.scalars(q))


def _next_to_close(db: Session, account_id: int, last: date | None) -> date | None:
    """The day to close next: the first day with movements after the last closed one, else today (None when today
    is closed already). Before the first closing, today: the first count starts the series."""
    if last is None:
        return today()
    moved = _moved_days(db, account_id, last, today())
    if moved:
        return moved[0]
    return today() if last < today() else None


def _closing_out(db: Session, c: TreasuryClosing, last_id: int | None) -> dict:
    from app.modules.identity import service as identity

    users = identity.user_names(db, {u for u in (c.closed_by, c.reopened_by) if u})
    journal = db.scalar(select(Journal.public_id).where(Journal.id == c.journal_id)) if c.journal_id else None
    return {
        "id": str(c.public_id),
        "branch_id": c.branch_id,
        "day": c.day,
        "book_balance": c.book_balance,
        "counted": c.counted,
        "denominations": c.denominations,
        "difference": c.difference,
        "note": c.note,
        "journal_id": str(journal) if journal else None,
        "closed_by": users.get(c.closed_by),
        "closed_at": c.closed_at,
        "reopened_by": users.get(c.reopened_by),
        "reopened_at": c.reopened_at,
        "reopen_reason": c.reopen_reason,
        "reopenable": c.reopened_at is None and c.id == last_id,
    }


def closing_day(db: Session, branch_public_id, *, day: date | None) -> dict:
    """What the count-and-close dialog shows: the day to close (the next one by default), the treasury's balance at
    its end, the last closed day and the days with movements still open."""
    branch = _branch(db, branch_public_id)
    acc = account(db, "treasury", branch_id=branch["id"])
    last = last_closed_day(db, [branch["id"]])
    suggested = _next_to_close(db, acc, last)
    day = day or suggested or today()
    out = {
        "branch": branch,
        "day": day,
        "book_balance": _book(db, acc, day),
        "last_closed_day": last,
        "next_day": suggested,
        "open_days": _moved_days(db, acc, last, today())[:62] if last is not None else [],
        "denominations": list(DENOMINATIONS),
    }
    db.commit()  # the account, made on first sight
    return out


def close_day(
    db: Session,
    branch_public_id,
    *,
    day: date,
    counted: Decimal,
    denominations: dict | None,
    note: str | None,
    actor_user_id: int,
) -> dict:
    """The cash counted in a branch's treasury at the end of a day, against its posted balance then (under the
    treasury's lock, so nothing moves it meanwhile): a difference is posted as a count_diff journal dated that day
    (treasury +/-, adjustments -/+; in the books on the cash differences account), with its explanation. Days are
    closed in order: no day while an earlier one with movements after the last closing is still open. A closed day
    takes no more treasury movements (_check_day)."""
    branch = _branch(db, branch_public_id)
    if day > today():
        raise AppError(422, "treasury_close_future")
    named, total = _denominations(denominations)
    if total is not None and total != counted:
        raise AppError(422, "denominations_mismatch", total=f"{total:.3f}", counted=f"{counted:.3f}")
    note = (note or "").strip() or None
    acc = account(db, "treasury", branch_id=branch["id"])
    lock_branches(db, treasury=[branch["id"]])
    last = _last_closing(db, branch["id"])
    if last is not None:
        if day <= last.day:
            raise AppError(409, "treasury_day_closed", day=day.isoformat())
        earlier = _moved_days(db, acc, last.day, day - timedelta(days=1))
        if earlier:
            raise AppError(409, "treasury_close_order", day=earlier[0].isoformat())
    book = _book(db, acc, day)
    difference = counted - book
    if difference and not note:
        raise AppError(422, "reason_required")
    closing_id = db.scalar(text("SELECT nextval(pg_get_serial_sequence('cash.treasury_closings', 'id'))"))
    journal = None
    if difference:
        from app.modules.finance import service as finance

        finance.check_books_date(db, day)  # the books enter it on that day
        journal = _journal(
            db,
            "count_diff",
            source_type="treasury_closing",
            source_id=closing_id,
            lines=[(acc, difference), (account(db, "adjustments"), -difference)],
            actor_user_id=actor_user_id,
            reason=note,
            post=True,
            business_date=day,
        )
    closing = TreasuryClosing(
        id=closing_id,
        branch_id=branch["id"],
        day=day,
        book_balance=book,
        counted=counted,
        denominations=named,
        difference=difference,
        note=note,
        journal_id=journal.id if journal else None,
        closed_by=actor_user_id,
    )
    db.add(closing)
    db.flush()
    db.refresh(closing)
    audit.record(
        db,
        action="cash.treasury_closed",
        entity_type="branch",
        entity_id=branch["public_id"],
        actor_user_id=actor_user_id,
        after={"day": day, "book": book, "counted": counted, "difference": difference, "note": note},
    )
    check_unclosed(db, [branch["id"]])
    if difference:
        check_treasury(db, [branch["id"]])
    db.commit()
    return _closing_out(db, closing, closing.id)


def reopen_closing(db: Session, public_id, *, reason: str, actor_user_id: int) -> dict:
    """A branch's last closing reopened (a wrong count): its difference journal reversed on the same day, which is
    open again; the closing stays in the list as reopened, with the reason."""
    closing = db.scalar(select(TreasuryClosing).where(TreasuryClosing.public_id == public_id))
    if closing is None:
        raise AppError(404, "treasury_closing_not_found")
    lock_branches(db, treasury=[closing.branch_id])
    db.refresh(closing)
    last = _last_closing(db, closing.branch_id)
    if closing.reopened_at is not None or last is None or last.id != closing.id:
        raise AppError(409, "treasury_closing_not_last")
    closing.reopened_by, closing.reopened_at, closing.reopen_reason = actor_user_id, utcnow(), reason
    db.flush()
    if closing.journal_id is not None:
        original = db.get(Journal, closing.journal_id)
        lines = list(
            db.execute(select(JournalLine.account_id, JournalLine.amount).where(JournalLine.journal_id == original.id))
        )
        treasury_acc = account(db, "treasury", branch_id=closing.branch_id)
        out = next((m for a, m in lines if a == treasury_acc and m > 0), None)
        if out is not None and _posted(db, treasury_acc) < out:  # a surplus taken back must still be there
            raise AppError(422, "treasury_insufficient")
        # dated as the difference it undoes: the day is open again, and closed again with its own count
        _journal(
            db,
            "reversal",
            source_type=original.source_type,
            source_id=original.source_id,
            lines=[(a, -m) for a, m in lines],
            actor_user_id=actor_user_id,
            reason=reason,
            reverses_id=original.id,
            post=True,
            business_date=closing.day,
        )
    branch = next(b for b in org.list_branches(db) if b["id"] == closing.branch_id)
    audit.record(
        db,
        action="cash.treasury_reopened",
        entity_type="branch",
        entity_id=branch["public_id"],
        actor_user_id=actor_user_id,
        after={"day": closing.day, "reason": reason},
    )
    check_unclosed(db, [closing.branch_id])
    check_treasury(db, [closing.branch_id])
    db.commit()
    return _closing_out(db, closing, None)


def closings(db: Session, branch_public_id, *, date_from: date, date_to: date) -> dict:
    """A branch treasury's closings of a period (newest first), the reopened ones too; only the last standing one
    may be reopened."""
    if date_to < date_from:
        raise AppError(422, "invalid_range")
    branch = _branch(db, branch_public_id)
    last = _last_closing(db, branch["id"])
    rows = db.scalars(
        select(TreasuryClosing)
        .where(TreasuryClosing.branch_id == branch["id"], TreasuryClosing.day.between(date_from, date_to))
        .order_by(TreasuryClosing.day.desc(), TreasuryClosing.id.desc())
    )
    return {
        "branch": branch,
        "last_closed_day": last.day if last else None,
        "lines": [_closing_out(db, c, last.id if last else None) for c in rows],
    }


def unclosed_days(db: Session, first: date, last: date) -> list[dict]:
    """For the month's close: per branch, the days of first..last with treasury movements not closed by a count."""
    out = []
    for b in org.list_branches(db):
        acc = db.scalar(select(Account.id).where(Account.kind == "treasury", Account.branch_id == b["id"]))
        if acc is None:
            continue
        closed = last_closed_day(db, [b["id"]])
        days = [d for d in _moved_days(db, acc, first - timedelta(days=1), last) if closed is None or d > closed]
        if days:
            out.append({"branch": b, "days": days})
    return out


def check_unclosed(db: Session, branch_ids: Iterable[int] | None = None) -> int:
    """treasury_not_closed for each branch whose treasury moved yesterday and yesterday is not closed by a count;
    closed by itself once it is. Returns the alerts standing."""
    yesterday = today() - timedelta(days=1)
    raised = 0
    for b in org.list_branches(db):
        if branch_ids is not None and b["id"] not in set(branch_ids):
            continue
        key = f"treasury_not_closed:{b['id']}"
        acc = db.scalar(select(Account.id).where(Account.kind == "treasury", Account.branch_id == b["id"]))
        closed = last_closed_day(db, [b["id"]])
        moved = acc is not None and yesterday in _moved_days(db, acc, yesterday - timedelta(days=1), yesterday)
        if moved and (closed is None or closed < yesterday):
            notifications.raise_alert(
                db,
                "treasury_not_closed",
                company_id=None,
                entity_type="branch",
                entity_id=b["public_id"],
                params={"branch": b["name"], "day": yesterday.isoformat()},
                dedupe_key=key,
                refresh=True,
            )
            raised += 1
        else:
            notifications.resolve(db, key)
    return raised


# ------------------------------------------------------------------ the treasury's deposit rule (settings cash)


def kuwait_weekday(day: date) -> int:
    """0 = Saturday .. 6 = Friday, the Kuwait week (settings cash.treasury_deposit_weekdays)."""
    return (day.weekday() + 2) % 7


def _treasury_balances(db: Session, branch_ids: Iterable[int] | None) -> list[tuple[dict, Decimal]]:
    branches = [b for b in org.list_branches(db) if branch_ids is None or b["id"] in set(branch_ids)]
    ids = {b["id"]: account(db, "treasury", branch_id=b["id"]) for b in branches}
    found = balances(db, ids.values())
    return [(b, found.get(ids[b["id"]], Balance(ZERO, ZERO)).posted) for b in branches]


def check_treasury(db: Session, branch_ids: Iterable[int] | None = None) -> None:
    """A branch treasury holding the deposit limit or more: treasury_deposit_due until a deposit (or any movement)
    brings it under; a treasury emptied closes its deposit-day alert. After every treasury movement, and nightly."""
    limit = org.get_section(db, "cash").treasury_deposit_limit
    for b, balance in _treasury_balances(db, branch_ids):
        key = f"treasury_deposit_due:{b['id']}"
        if limit > 0 and balance >= limit:
            notifications.raise_alert(
                db,
                "treasury_deposit_due",
                company_id=None,
                entity_type="branch",
                entity_id=b["public_id"],
                params={"branch": b["name"], "balance": f"{balance:.3f}", "limit": f"{limit:.3f}"},
                dedupe_key=key,
                refresh=True,
            )
        else:
            notifications.resolve(db, key)
        if balance <= 0:
            notifications.resolve(db, f"treasury_deposit_day:{b['id']}")


def recheck_deposit_day(db: Session) -> None:
    """The deposit days changed: today no longer one of them closes today's deposit-day alerts."""
    if kuwait_weekday(today()) not in org.get_section(db, "cash").treasury_deposit_weekdays:
        notifications.resolve(db, "treasury_deposit_day:", prefix=True)


def scan_treasury(db: Session, *, moment: str) -> int:
    """moment "morning" (07:00 Kuwait): on a deposit day, treasury_deposit_day for each branch whose treasury holds
    cash; "night" (end of the day): the day's deposit-day alerts close. Both check the limit again. Returns the
    deposit-day alerts raised."""
    raised = 0
    if moment == "night":
        notifications.resolve(db, "treasury_deposit_day:", prefix=True)
    elif kuwait_weekday(today()) in org.get_section(db, "cash").treasury_deposit_weekdays:
        for b, balance in _treasury_balances(db, None):
            if balance > 0:
                notifications.raise_alert(
                    db,
                    "treasury_deposit_day",
                    company_id=None,
                    entity_type="branch",
                    entity_id=b["public_id"],
                    params={"branch": b["name"], "balance": f"{balance:.3f}"},
                    dedupe_key=f"treasury_deposit_day:{b['id']}",
                    refresh=True,
                )
                raised += 1
    check_treasury(db)
    if moment != "night":
        check_unclosed(db)  # yesterday's treasury, moved and not counted and closed
    db.commit()
    return raised


# ------------------------------------------------------------------ invariants (nightly)


def journal_drivers(db: Session, journal_ids: Iterable[int]) -> dict[int, int]:
    """The driver each journal moved money for (his account's line), for finance's account statements."""
    ids = list(set(journal_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(JournalLine.journal_id, Account.driver_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(JournalLine.journal_id.in_(ids), Account.driver_id.is_not(None))
    )
    return {j: d for j, d in rows}


def posted_journals(db: Session, first: date, last: date) -> list[dict]:
    """Posted journals of business dates first..last with their lines by account kind, for finance's entries: every
    collection, receipt, bank deposit, adjustment, settlement, write-off, opening balance and reversal."""
    journals = list(
        db.scalars(
            select(Journal)
            .where(Journal.status == "posted", Journal.business_date.between(first, last))
            .order_by(Journal.id)
        )
    )
    if not journals:
        return []
    lines: dict[int, list[dict]] = {j.id: [] for j in journals}
    for journal_id, amount, kind, driver_id, branch_id in db.execute(
        select(JournalLine.journal_id, JournalLine.amount, Account.kind, Account.driver_id, Account.branch_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(JournalLine.journal_id.in_(list(lines)))
        .order_by(JournalLine.journal_id, JournalLine.amount.desc())
    ):
        lines[journal_id].append({"kind": kind, "amount": amount, "driver_id": driver_id, "branch_id": branch_id})
    reversed_kinds = dict(
        db.execute(
            select(Journal.id, Journal.kind).where(Journal.id.in_({j.reverses_id for j in journals if j.reverses_id}))
        ).all()
    )
    return [
        {
            "id": j.id,
            "public_id": str(j.public_id),
            "kind": j.kind,
            "reverses_kind": reversed_kinds.get(j.reverses_id),
            "date": j.business_date,
            "reason": j.reason,
            "lines": lines[j.id],
        }
        for j in journals
    ]


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
