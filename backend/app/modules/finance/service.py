"""Finance (BRD FR-FIN-01..05): the chart of accounts and its roles, expense types, expenses with their files and
payment, and the journal entries made from the system's documents (app.modules.finance.posting): made as drafts,
approved by the accountant, never changed once approved (a reversing entry corrects one), exported to Excel."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.finance import periods, posting
from app.modules.finance.models import (
    ENTRY_SEQ,
    Account,
    AccountRole,
    Entry,
    EntryLine,
    Expense,
    ExpenseFile,
    ExpenseType,
)
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.org import service as org
from app.modules.people import service as people

MAX_POST_DAYS = 93
EXPORT_MAX_LINES = 50_000
ZERO = Decimal("0.000")


def _span(first: date, last: date, days: int) -> None:
    if last < first:
        raise AppError(422, "invalid_range")
    if (last - first).days >= days:
        raise AppError(422, "range_too_long_days", days=days)


def _need_all_companies(all_companies: bool) -> None:
    """The ledger is the whole business's: only a user over every company keeps it."""
    if not all_companies:
        raise AppError(403, "all_companies_required")


# ------------------------------------------------------------------ how the books are kept (settings section finance)


def books(db: Session):
    return org.get_section(db, "finance")


def fiscal_year_start(db: Session, day: date | None = None) -> date:
    """The first day of the fiscal year day falls in (today's by default)."""
    day = day or today()
    m = books(db).fiscal_year_start_month
    return date(day.year if day.month >= m else day.year - 1, m, 1)


def config(db: Session) -> dict:
    b = books(db)
    return {
        "entry_approval": b.entry_approval,
        "fiscal_year_start_month": b.fiscal_year_start_month,
        "fiscal_year_start": fiscal_year_start(db),
        "books_start_date": b.books_start_date,
        "opening_date": b.books_start_date - timedelta(days=1) if b.books_start_date else None,
    }


def _check_date(db: Session, day: date) -> None:
    """Nothing is entered before the books start in this system: what came before is in the opening balances."""
    start = books(db).books_start_date
    if start and day < start:
        raise AppError(422, "before_books_start", date=start.isoformat())


def check_books_date(db: Session, day: date) -> None:
    """For other modules: refused (before_books_start) when a document of that day would never be entered."""
    _check_date(db, day)


def month_closed(db: Session, day: date) -> bool:
    """For other modules: whether the month of `day` is closed, holding the month's shared lock (see
    check_open_month)."""
    return periods.is_closed(db, day)


def check_open_month(db: Session, day: date) -> None:
    """For other modules: refused (409 period_closed) when the month of `day` is closed; holds the month's shared
    lock until the transaction ends, so the month cannot close before what the caller writes is in."""
    periods.check_open(db, day)


def check_books_start_change(db: Session, old: date | None, new: date | None) -> None:
    """The books start moves only while nothing hangs on it: no opening entry standing, and no entry dated between the
    two dates (an earlier start would enter documents the opening already counts; a later one would leave entries
    before the start)."""
    if old == new:
        return
    if (
        db.scalar(select(Entry.id).where(Entry.source_kind == "opening", Entry.reversed_by_id.is_(None)).limit(1))
        is not None
    ):
        raise AppError(409, "books_start_locked")
    if old and new:
        lo, hi = min(old, new), max(old, new)
        hit = db.scalar(
            select(Entry.id)
            .where(Entry.entry_date >= lo, Entry.entry_date < hi, Entry.source_kind != "reversal")
            .limit(1)
        )
        if hit is not None:
            raise AppError(409, "books_start_locked")


def _auto(db: Session) -> bool:
    return books(db).entry_approval == "auto"


def _approve_by_system(db: Session, rows: list[Entry]) -> None:
    """entry_approval "auto": the entries just made are approved at once, by the system (approved_by NULL)."""
    if not rows:
        return
    db.flush()  # their lines first: an entry is approved only with balanced lines (finance.guard_entry)
    now = utcnow()
    for e in rows:
        e.status, e.approved_by, e.approved_at = "approved", None, now
    db.flush()
    audit.record(
        db,
        action="finance.entries.approved",
        entity_type="entry",
        actor_user_id=None,
        after={"numbers": sorted(e.number for e in rows), "auto": True},
    )


def _name(db: Session, name: dict) -> str:
    lang = i18n.default_language(db).code
    return name.get(lang) or next(iter(name.values()), "")


# ------------------------------------------------------------------ the chart of accounts


def _account_out(a: Account, roles: dict[int, list[str]], used: set[int]) -> dict:
    return {
        "id": a.id,
        "code": a.code,
        "name": a.name,
        "type": a.type,
        "active": a.active,
        "roles": sorted(roles.get(a.id, [])),
        "used": a.id in used,
        "version": a.version,
    }


def list_accounts(db: Session) -> list[dict]:
    roles: dict[int, list[str]] = defaultdict(list)
    for role, account_id in db.execute(select(AccountRole.role, AccountRole.account_id)):
        roles[account_id].append(role)
    used = set(db.scalars(select(EntryLine.account_id).distinct()))
    return [_account_out(a, roles, used) for a in db.scalars(select(Account).order_by(Account.code))]


def _account(db: Session, account_id: int, *, lock: bool = False) -> Account:
    account = db.get(Account, account_id, with_for_update=lock)
    if account is None:
        raise AppError(404, "account_not_found")
    return account


def create_account(db: Session, data: dict, *, actor_user_id: int) -> dict:
    account = Account(code=data["code"], name=data["name"], type=data["type"])
    db.add(account)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if violated_constraint(e) == "accounts_code_key":
            raise AppError(409, "account_code_taken", code=data["code"]) from None
        raise
    audit.record(
        db,
        action="finance.account.created",
        entity_type="account",
        entity_id=account.id,
        actor_user_id=actor_user_id,
        after={"code": account.code, "type": account.type},
    )
    db.commit()
    return next(a for a in list_accounts(db) if a["id"] == account.id)


def update_account(db: Session, account_id: int, changes: dict, *, version: int, actor_user_id: int) -> dict:
    """Its name always; its code and type only while no entry uses it (the exported entries carry the code); closed
    only when no role and no expense type points at it."""
    account = _account(db, account_id, lock=True)
    if account.version != version:
        raise AppError(409, "version_conflict")
    used = db.scalar(select(EntryLine.account_id).where(EntryLine.account_id == account.id).limit(1)) is not None
    if used and any(k in changes and changes[k] != getattr(account, k) for k in ("code", "type")):
        raise AppError(409, "account_in_use")
    if changes.get("active") is False:
        pointed = db.scalar(select(AccountRole.role).where(AccountRole.account_id == account.id).limit(1))
        typed = db.scalar(select(ExpenseType.code).where(ExpenseType.account_id == account.id, ExpenseType.active))
        if pointed or typed:
            raise AppError(409, "account_in_role", role=pointed or typed)
    before = {k: getattr(account, k) for k in changes}
    for k, v in changes.items():
        setattr(account, k, v)
    account.version += 1
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if violated_constraint(e) == "accounts_code_key":
            raise AppError(409, "account_code_taken", code=changes["code"]) from None
        raise
    audit.record(
        db,
        action="finance.account.updated",
        entity_type="account",
        entity_id=account.id,
        actor_user_id=actor_user_id,
        before=before,
        after=changes,
    )
    db.commit()
    return next(a for a in list_accounts(db) if a["id"] == account.id)


def roles(db: Session) -> list[dict]:
    mapped = dict(db.execute(select(AccountRole.role, AccountRole.account_id)).tuples().all())
    return [{"role": r, "account_id": mapped.get(r)} for r in posting.ROLES]


def set_roles(db: Session, mapping: dict[str, int], *, actor_user_id: int) -> list[dict]:
    """Which account each posting uses. Entries already made keep theirs: drafts are made again, approved ones are
    reversed and made again."""
    unknown = set(mapping) - set(posting.ROLES)
    if unknown:
        raise AppError(422, "unknown_account_role", role=sorted(unknown)[0])
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(set(mapping.values()))))}
    before = dict(db.execute(select(AccountRole.role, AccountRole.account_id)).tuples().all())
    for role, account_id in mapping.items():
        account = accounts.get(account_id)
        if account is None:
            raise AppError(404, "account_not_found")
        if not account.active:
            raise AppError(422, "account_inactive", code=account.code)
        row = db.get(AccountRole, role)
        if row is None:
            db.add(AccountRole(role=role, account_id=account_id))
        else:
            row.account_id = account_id
    changed = {r: a for r, a in mapping.items() if before.get(r) != a}
    if changed:
        audit.record(
            db,
            action="finance.roles.updated",
            entity_type="account",
            actor_user_id=actor_user_id,
            before={r: before.get(r) for r in changed},
            after=changed,
        )
    db.commit()
    return roles(db)


# ------------------------------------------------------------------ expense types


def _type_out(t: ExpenseType) -> dict:
    return {
        "id": t.id,
        "code": t.code,
        "name": t.name,
        "account_id": t.account_id,
        "active": t.active,
        "sort_order": t.sort_order,
    }


def list_types(db: Session) -> list[dict]:
    return [_type_out(t) for t in db.scalars(select(ExpenseType).order_by(ExpenseType.sort_order, ExpenseType.id))]


def _active_account(db: Session, account_id: int) -> Account:
    account = _account(db, account_id)
    if not account.active:
        raise AppError(422, "account_inactive", code=account.code)
    return account


def create_type(db: Session, data: dict, *, actor_user_id: int) -> dict:
    _active_account(db, data["account_id"])
    t = ExpenseType(**data)
    db.add(t)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if violated_constraint(e) == "expense_types_code_key":
            raise AppError(409, "expense_type_code_taken", code=data["code"]) from None
        raise
    audit.record(
        db,
        action="finance.expense_type.created",
        entity_type="expense_type",
        entity_id=t.id,
        actor_user_id=actor_user_id,
        after=data,
    )
    db.commit()
    return _type_out(t)


def update_type(db: Session, type_id: int, changes: dict, *, actor_user_id: int) -> dict:
    t = db.get(ExpenseType, type_id, with_for_update=True)
    if t is None:
        raise AppError(404, "expense_type_not_found")
    if "account_id" in changes:
        _active_account(db, changes["account_id"])
    before = {k: getattr(t, k) for k in changes}
    for k, v in changes.items():
        setattr(t, k, v)
    audit.record(
        db,
        action="finance.expense_type.updated",
        entity_type="expense_type",
        entity_id=t.id,
        actor_user_id=actor_user_id,
        before=before,
        after=changes,
    )
    db.commit()
    return _type_out(t)


# ------------------------------------------------------------------ expenses


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Expense.company_id.in_(list(company_ids)))


def _get(db: Session, public_id, *, all_companies: bool, company_ids: Iterable[int], lock: bool = False) -> Expense:
    q = _scoped(select(Expense).where(Expense.public_id == public_id), all_companies, company_ids)
    expense = db.scalar(q.with_for_update() if lock else q)
    if expense is None:
        raise AppError(404, "expense_not_found")
    return expense


def _expense_out(db: Session, rows: list[Expense]) -> list[dict]:
    from app.modules.fleet import service as fleet
    from app.modules.maintenance import service as maintenance

    types = {t.id: t for t in db.scalars(select(ExpenseType).where(ExpenseType.id.in_({e.type_id for e in rows})))}
    vehicles = fleet.vehicle_cards(db, {e.vehicle_id for e in rows if e.vehicle_id})
    employees = people.names(db, {x for e in rows for x in (e.employee_id, e.petty_employee_id) if x})
    centers = maintenance.centers_brief(db, {e.center_id for e in rows if e.center_id})
    users = identity.user_names(db, {u for e in rows for u in (e.created_by, e.decided_by, e.paid_by) if u})
    attached: dict[int, list[str]] = defaultdict(list)
    for expense_id, sha in db.execute(
        select(ExpenseFile.expense_id, ExpenseFile.sha256)
        .where(ExpenseFile.expense_id.in_([e.id for e in rows]))
        .order_by(ExpenseFile.expense_id, ExpenseFile.position)
    ):
        attached[expense_id].append(sha)
    out = []
    for e in rows:
        t = types[e.type_id]
        vehicle = vehicles.get(e.vehicle_id)
        center = centers.get(e.center_id)
        out.append(
            {
                "id": str(e.public_id),
                "number": e.number,
                "company_id": e.company_id,
                "branch_id": e.branch_id,
                "type": {"id": t.id, "code": t.code, "name": t.name},
                "expense_date": e.expense_date,
                "amount": e.amount,
                "quantity": e.quantity,
                "payment_method": e.payment_method,
                "supplier": e.supplier,
                "reference_no": e.reference_no,
                "vehicle": {"id": vehicle["id"], "plate_number": vehicle["plate_number"]} if vehicle else None,
                "employee": employees.get(e.employee_id),
                "petty_employee": employees.get(e.petty_employee_id),
                "center": {"id": center["id"], "name": center["name"]} if center else None,
                "notes": e.notes,
                "status": e.status,
                "files": attached.get(e.id, []),
                "created_by": users.get(e.created_by),
                "created_at": e.created_at,
                "decided_by": users.get(e.decided_by),
                "decided_at": e.decided_at,
                "decision_note": e.decision_note,
                "cancel_reason": e.cancel_reason,
                "paid_from": e.paid_from,
                "paid_at": e.paid_at,
                "paid_by": users.get(e.paid_by),
                "payment_ref": e.payment_ref,
                "unpaid": e.payment_method == "payable" and e.status == "approved" and e.paid_at is None,
                "version": e.version,
            }
        )
    return out


def _audit(db: Session, action: str, e: Expense, *, actor_user_id: int, after: dict | None = None) -> None:
    audit.record(
        db,
        action=f"finance.expense.{action}",
        entity_type="expense",
        entity_id=e.public_id,
        actor_user_id=actor_user_id,
        company_id=e.company_id,
        after={"number": e.number, "amount": e.amount, "status": e.status, **(after or {})},
    )


def create_expense(db: Session, data: dict, *, actor_user_id: int, all_companies: bool, company_ids) -> dict:
    """An expense, linked as it says to a vehicle, an employee or a maintenance center of the same company."""
    from app.modules.fleet import service as fleet
    from app.modules.maintenance import service as maintenance

    scope = {"all_companies": all_companies, "company_ids": company_ids}
    company_id = data["company_id"]
    if not org.company_ids_exist(db, [company_id]) or not (all_companies or company_id in set(company_ids)):
        raise AppError(404, "company_not_found")
    t = db.get(ExpenseType, data["type_id"])
    if t is None or not t.active:
        raise AppError(404, "expense_type_not_found")
    vehicle = fleet.vehicle_ref_by_public_id(db, data["vehicle_id"], **scope) if data.get("vehicle_id") else None
    employee = people.ref_by_public_id(db, data["employee_id"], **scope) if data.get("employee_id") else None
    center = maintenance.center_brief(db, data["center_id"]) if data.get("center_id") else None
    for linked in (vehicle, employee):
        if linked is not None and linked.company_id != company_id:
            raise AppError(422, "expense_company_mismatch")
    for sha in data.get("files", []):
        files.get(db, sha)
    branch_id = data.get("branch_id")
    if branch_id is not None:
        _check_branch(db, branch_id)
    elif data["payment_method"] == "treasury":  # the money comes out of a branch's treasury: which one
        raise AppError(422, "expense_branch_required")
    if data["payment_method"] == "treasury":
        _treasury_day(db, data["expense_date"], branch_id)
    holder = _petty_holder(db, data, all_companies) if data["payment_method"] == "petty" else None
    periods.check_open(db, data["expense_date"])  # it enters the books on its date
    expense = Expense(
        company_id=company_id,
        branch_id=branch_id,
        type_id=t.id,
        expense_date=data["expense_date"],
        amount=data["amount"],
        quantity=data.get("quantity"),
        payment_method=data["payment_method"],
        petty_employee_id=holder.id if holder else None,
        supplier=data.get("supplier"),
        reference_no=data.get("reference_no"),
        vehicle_id=vehicle.id if vehicle else None,
        employee_id=employee.id if employee else None,
        center_id=center["id"] if center else None,
        notes=data.get("notes"),
        created_by=actor_user_id,
    )
    db.add(expense)
    db.flush()
    for n, sha in enumerate(dict.fromkeys(data.get("files", []))):
        db.add(ExpenseFile(expense_id=expense.id, sha256=sha, position=n))
    db.refresh(expense)
    approvals.submitted(db, "expense", **_approval(expense), actor_user_id=actor_user_id)
    _audit(db, "created", expense, actor_user_id=actor_user_id)
    db.commit()
    return _expense_out(db, [expense])[0]


def list_expenses(
    db: Session,
    *,
    status: str | None = None,
    type_id: int | None = None,
    vehicle_id=None,
    unpaid: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
    all_companies: bool,
    company_ids,
) -> list[dict]:
    from app.modules.fleet import service as fleet

    q = _scoped(select(Expense), all_companies, company_ids)
    if status:
        q = q.where(Expense.status.in_(status.split(",")))
    if type_id:
        q = q.where(Expense.type_id == type_id)
    if vehicle_id:
        v = fleet.vehicle_ref_by_public_id(db, vehicle_id, all_companies=all_companies, company_ids=company_ids)
        q = q.where(Expense.vehicle_id == v.id)
    if unpaid:
        q = q.where(Expense.payment_method == "payable", Expense.status == "approved", Expense.paid_at.is_(None))
    if date_from:
        q = q.where(Expense.expense_date >= date_from)
    if date_to:
        q = q.where(Expense.expense_date <= date_to)
    rows = list(
        db.scalars(q.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(min(limit, 500)).offset(offset))
    )
    return _expense_out(db, rows)


def get_expense(db: Session, public_id, **scope) -> dict:
    return _expense_out(db, [_get(db, public_id, **scope)])[0]


def expense_file(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    expense = _get(db, public_id, **scope)
    if db.get(ExpenseFile, (expense.id, sha256)) is None:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def _check_branch(db: Session, branch_id: int) -> None:
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")


def _treasury_day(db: Session, day: date, branch_id: int | None = None) -> None:
    """Money out of the treasury is dated as its entry in the books: never before the books start (the books would
    never count it while the screen does), never in the future, never in a day the branch closed by its count."""
    from app.modules.cash import service as cash

    _check_date(db, day)
    if day > today():
        raise AppError(422, "treasury_date_future")
    closed = cash.last_closed_day(db, [branch_id]) if branch_id is not None else None
    if closed is not None and day <= closed:
        raise AppError(409, "treasury_day_closed", day=day.isoformat())


def _disburse(db: Session, expense: Expense, *, day: date, actor_user_id: int) -> None:
    """The expense's money leaves its branch's treasury now (approved paid from it, or paid later from it): the
    treasury on screen goes down with the books (cash ledger disbursement, refused when the treasury holds less),
    dated as the books date it: the expense's date, or the day it is paid."""
    from app.modules.cash import service as cash

    _treasury_day(db, day)

    t = db.get(ExpenseType, expense.type_id)
    first_file = db.scalar(
        select(ExpenseFile.sha256).where(ExpenseFile.expense_id == expense.id).order_by(ExpenseFile.position).limit(1)
    )
    cash.disburse(
        db,
        branch_id=expense.branch_id,
        amount=expense.amount,
        business_date=day,
        source_type="expense",
        source_id=expense.id,
        reason=f"EXP-{expense.number} · {_name(db, t.name)}",
        attachment_sha256=first_file,
        actor_user_id=actor_user_id,
    )


def petty_role_ready(db: Session) -> bool:
    """Whether the books can enter a petty cash custody: its role (petty_cash) on an open account."""
    account = posting.role_accounts(db).get("petty_cash")
    return account is not None and account.active


def check_petty_role(db: Session) -> None:
    """For other modules: refused (petty_role_missing) while the books cannot enter a custody."""
    if not petty_role_ready(db):
        raise AppError(422, "petty_role_missing")


def _petty_holder(db: Session, data: dict, all_companies: bool) -> people.EmployeeRef:
    """Paid from an employee's petty cash custody: his, named, one who holds a custody; the custody is not a
    company's, so an all-companies user only. Dated as money out of the treasury is (books start, not ahead)."""
    from app.modules.cash import service as cash

    if not all_companies:
        raise AppError(403, "company_out_of_scope")
    if not data.get("petty_employee_id"):
        raise AppError(422, "expense_petty_holder_required")
    check_petty_role(db)
    holder = people.ref_by_public_id(db, data["petty_employee_id"], all_companies=True, company_ids=[])
    if not cash.is_petty_holder(db, holder.id):
        raise AppError(422, "petty_holder_unknown")
    _treasury_day(db, data["expense_date"])
    return holder


def _disburse_petty(db: Session, expense: Expense, *, actor_user_id: int) -> None:
    """Approved: the money leaves the holder's custody now (refused when he holds less), dated as the books date the
    expense."""
    from app.modules.cash import service as cash

    _treasury_day(db, expense.expense_date)
    t = db.get(ExpenseType, expense.type_id)
    first_file = db.scalar(
        select(ExpenseFile.sha256).where(ExpenseFile.expense_id == expense.id).order_by(ExpenseFile.position).limit(1)
    )
    cash.petty_disburse(
        db,
        employee_id=expense.petty_employee_id,
        amount=expense.amount,
        business_date=expense.expense_date,
        source_type="expense",
        source_id=expense.id,
        reason=f"EXP-{expense.number} · {_name(db, t.name)}",
        attachment_sha256=first_file,
        actor_user_id=actor_user_id,
    )


def advances_from_treasury(db: Session) -> bool:
    """Whether an advance is paid out of the treasury in the books: its role (deduction_advance) is on the treasury's
    account, as the default chart has it. Then the advance is a disbursement of the employee's branch treasury."""
    roles = posting.role_accounts(db)
    advance, treasury = roles.get("deduction_advance"), roles.get("treasury")
    return advance is not None and treasury is not None and advance.id == treasury.id


def _approval(expense: Expense) -> dict:
    return {
        "document_id": expense.id,
        "document_key": expense.public_id,
        "document_ref": f"EXP-{expense.number}",
        "company_id": expense.company_id,
        "amount": expense.amount,
    }


def _petty_scope(expense: Expense, scope: dict) -> None:
    """An expense paid from a petty cash custody moves the custody, which is not a company's: an all-companies user
    decides or cancels it."""
    if expense.payment_method == "petty" and not scope.get("all_companies"):
        raise AppError(403, "company_out_of_scope")


def decide_expense(db: Session, public_id, *, approve: bool, note: str | None, actor_user_id: int, **scope) -> dict:
    expense = _get(db, public_id, lock=True, **scope)
    _petty_scope(expense, scope)
    if expense.status != "pending":
        raise AppError(409, "expense_not_pending", status=expense.status)
    if not approve and not note:
        raise AppError(422, "reason_required")
    if approve:
        periods.check_open(db, expense.expense_date)  # it enters the books on its date
    if not approvals.gate(
        db, "expense", **_approval(expense), actor_user_id=actor_user_id, approve=approve, reason=note
    ):
        db.commit()  # this step recorded; the expense waits for the next one
        return _expense_out(db, [expense])[0]
    # an expense entered before expenses named their branch (no branch) keeps the old way: the books only
    if approve and expense.payment_method == "treasury" and expense.branch_id is not None:
        _disburse(db, expense, day=expense.expense_date, actor_user_id=actor_user_id)
    if approve and expense.payment_method == "petty":
        _disburse_petty(db, expense, actor_user_id=actor_user_id)
    expense.status = "approved" if approve else "rejected"
    expense.decided_by, expense.decided_at, expense.decision_note = actor_user_id, utcnow(), note
    expense.version += 1
    _audit(db, expense.status, expense, actor_user_id=actor_user_id, after={"note": note})
    db.commit()
    return _expense_out(db, [expense])[0]


def cancel_expense(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """A wrong entry, before or after approval (not once paid later): its journal entry, if made, is then listed to
    be reversed; the money an approved one took from the treasury goes back to it (its disbursement reversed, with
    the reason), in the same transaction."""
    from app.modules.cash import service as cash

    expense = _get(db, public_id, lock=True, **scope)
    _petty_scope(expense, scope)
    if expense.status not in ("pending", "approved") or expense.paid_at is not None:
        raise AppError(409, "expense_not_cancellable", status=expense.status)
    if expense.status == "approved":
        cash.undo_disbursement(
            db, source_type="expense", source_id=expense.id, reason=reason, actor_user_id=actor_user_id
        )
    expense.status, expense.cancel_reason = "cancelled", reason  # an approved one keeps who approved it, and when
    expense.version += 1
    approvals.withdrawn(db, "expense", [expense.id])
    _audit(db, "cancelled", expense, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _expense_out(db, [expense])[0]


def pay_expense(
    db: Session,
    public_id,
    *,
    paid_from: str,
    payment_ref: str | None,
    actor_user_id: int,
    branch_id: int | None = None,
    **scope,
) -> dict:
    """A supplier's invoice entered to be paid later, paid now from the bank, or from a branch's treasury (which
    then goes down by it)."""
    expense = _get(db, public_id, lock=True, **scope)
    if expense.payment_method != "payable" or expense.status != "approved" or expense.paid_at is not None:
        raise AppError(409, "expense_not_payable")
    if branch_id is not None:
        _check_branch(db, branch_id)
        expense.branch_id = branch_id
    if paid_from == "treasury":
        if expense.branch_id is None:
            raise AppError(422, "expense_branch_required")
        _disburse(db, expense, day=today(), actor_user_id=actor_user_id)  # entered on the Kuwait day it is paid
    expense.paid_from, expense.paid_at, expense.paid_by, expense.payment_ref = (
        paid_from,
        utcnow(),
        actor_user_id,
        payment_ref,
    )
    expense.version += 1
    _audit(db, "paid", expense, actor_user_id=actor_user_id, after={"paid_from": paid_from, "payment_ref": payment_ref})
    db.commit()
    return _expense_out(db, [expense])[0]


# ------------------------------------------------------------------ journal entries


def _describe(db: Session, doc: posting.Doc) -> str:
    lang = i18n.default_language(db).code
    params = dict(doc.params)
    if "kind" in params:
        params["kind"] = i18n.t(db, lang, f"journal_kind.{params['kind']}")
    if "source" in params:
        params["source"] = i18n.t(db, lang, f"deduction_source.{params['source']}")
    if isinstance(params.get("type"), dict):
        params["type"] = params["type"].get(lang) or next(iter(params["type"].values()), "")
    text = i18n.t(db, lang, f"finance_source.{doc.text}", **params)
    return " ".join(text.split()).strip(" —:")


def post(db: Session, first: date, last: date, *, actor_user_id: int, all_companies: bool, **_) -> dict:
    """Draft entries for the documents of first..last without one; and the entries whose document changed since
    (cancelled, reopened, a different amount), to be reversed (FR-FIN-03). Run again at will: nothing is entered
    twice."""
    _need_all_companies(all_companies)
    _span(first, last, MAX_POST_DAYS)
    start = books(db).books_start_date
    if start and first < start:  # documents before the books start are in the opening balances, not entered
        first = start
        if last < first:
            return {"created": 0, "by_kind": {}, "stale": [], "errors": []}
    missing, stale = compare(db, first, last)
    roles = posting.role_accounts(db)
    created: dict[str, int] = defaultdict(int)
    errors, made = [], []
    # a closed month takes no entry: a document of it that changed since (a deduction cancelled after payroll took
    # part of it...) is entered on the first day of the first open month after it, saying which day it is for; what
    # still cannot be entered is reported, never skipped silently
    months = {d.day.replace(day=1) for d in missing}
    closed = {m for m in months if periods.is_closed(db, m)}
    lang = i18n.default_language(db).code
    for doc in missing:
        description = None
        if doc.day.replace(day=1) in closed:
            moved = periods.first_open_month(db, doc.day)
            if moved is None:
                errors.append({"source_ref": doc.ref, "code": "period_closed", "params": {"month": f"{doc.day:%Y-%m}"}})
                continue
            original = doc.day
            description = _describe(db, doc)
            doc.day = moved
            note = i18n.t(db, lang, "finance_source.original_date", date=original.isoformat())
            description = f"{description} ({note})"
        try:
            with db.begin_nested():
                made.append(
                    posting.write(
                        db,
                        doc,
                        description=description or _describe(db, doc),
                        roles=roles,
                        actor_user_id=actor_user_id,
                    )
                )
            created[doc.kind] += 1
        except AppError as e:
            errors.append({"source_ref": doc.ref, "code": e.code, "params": e.params})
    if created:
        audit.record(
            db,
            action="finance.entries.posted",
            entity_type="entry",
            actor_user_id=actor_user_id,
            after={"from": first, "to": last, "created": dict(created)},
        )
    if _auto(db):
        _approve_by_system(db, made)
    db.commit()
    return {"created": sum(created.values()), "by_kind": dict(created), "stale": stale, "errors": errors}


def compare(db: Session, first: date, last: date) -> tuple[list[posting.Doc], list[dict]]:
    """The documents of first..last that make an entry and have none yet, and the live entries whose document changed
    since (or is gone): what a posting would make, and what it lists to reverse. Writes nothing."""
    docs = posting.documents(db, first, last)
    live = {
        (e.source_kind, e.source_id): e
        for e in db.scalars(
            select(Entry).where(
                Entry.source_kind.not_in(("reversal", "manual", "opening")),  # written by hand: no document to match
                Entry.reversed_by_id.is_(None),
                or_(
                    Entry.entry_date.between(first, last),
                    *[
                        (Entry.source_kind == k) & Entry.source_id.in_(ids)
                        for k, ids in _by_kind((d.kind, d.id) for d in docs).items()
                    ],
                ),
            )
        )
    }
    totals = dict(
        db.execute(
            select(EntryLine.entry_id, func.sum(EntryLine.debit))
            .where(EntryLine.entry_id.in_([e.id for e in live.values()]))
            .group_by(EntryLine.entry_id)
        ).all()
    )
    stale, missing, seen = [], [], set()
    for doc in docs:
        key = (doc.kind, doc.id)
        seen.add(key)
        entry = live.get(key)
        if entry is not None:
            if totals.get(entry.id, ZERO) != doc.total:
                stale.append(_stale(entry, totals.get(entry.id, ZERO), doc.total))
            continue
        if doc.total != ZERO:
            missing.append(doc)
    for key, entry in live.items():
        if key not in seen and first <= entry.entry_date <= last:
            stale.append(_stale(entry, totals.get(entry.id, ZERO), ZERO))
    return missing, stale


def _by_kind(keys: Iterable[tuple[str, int]]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for kind, i in keys:
        out[kind].append(i)
    return out


def _stale(entry: Entry, entered: Decimal, now: Decimal) -> dict:
    return {
        "id": str(entry.public_id),
        "number": entry.number,
        "source_ref": entry.source_ref,
        "status": entry.status,
        "entered": entered,
        "document": now,
    }


def _entry_scope(q, all_companies: bool, company_ids):
    """A company-limited user sees his companies' entries and the shared ones (a branch's treasury and bank)."""
    if all_companies:
        return q
    return q.where(or_(Entry.company_id.is_(None), Entry.company_id.in_(list(company_ids))))


def _entries_out(db: Session, rows: list[Entry], *, with_lines: bool) -> list[dict]:
    ids = [e.id for e in rows]
    lines: dict[int, list[dict]] = defaultdict(list)
    sums: dict[int, Decimal] = defaultdict(lambda: ZERO)
    if ids:
        found = db.execute(
            select(EntryLine, Account)
            .join(Account, Account.id == EntryLine.account_id)
            .where(EntryLine.entry_id.in_(ids))
            .order_by(EntryLine.entry_id, EntryLine.line_no)
        ).all()
        named = people.names(db, {ln.employee_id for ln, _ in found if ln.employee_id}) if with_lines else {}
        for ln, a in found:
            sums[ln.entry_id] += ln.debit
            lines[ln.entry_id].append(
                {
                    "account": {"id": a.id, "code": a.code, "name": a.name},
                    "debit": ln.debit,
                    "credit": ln.credit,
                    "memo": ln.memo,
                    "employee": named.get(ln.employee_id),
                }
            )
    numbers = dict(
        db.execute(
            select(Entry.id, Entry.number).where(
                Entry.id.in_({x for e in rows for x in (e.reverses_id, e.reversed_by_id) if x})
            )
        ).all()
    )
    users = identity.user_names(db, {u for e in rows for u in (e.created_by, e.approved_by) if u})
    return [
        {
            "id": str(e.public_id),
            "number": e.number,
            "entry_date": e.entry_date,
            "source_kind": e.source_kind,
            "source_ref": e.source_ref,
            "company_id": e.company_id,
            "description": e.description,
            "status": e.status,
            "amount": sums[e.id],
            "reverses": numbers.get(e.reverses_id),
            "reversed_by": numbers.get(e.reversed_by_id),
            "reason": e.reason,
            "created_by": users.get(e.created_by),
            "created_at": e.created_at,
            "approved_by": users.get(e.approved_by),
            "approved_at": e.approved_at,
            "lines": lines[e.id] if with_lines else None,
        }
        for e in rows
    ]


def _entries_query(
    *,
    status: str | None = None,
    source_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: int | None = None,
    q: str | None = None,
    all_companies: bool,
    company_ids,
):
    query = _entry_scope(select(Entry), all_companies, company_ids)
    if status:
        query = query.where(Entry.status.in_(status.split(",")))
    if source_kind:
        query = query.where(Entry.source_kind == source_kind)
    if date_from:
        query = query.where(Entry.entry_date >= date_from)
    if date_to:
        query = query.where(Entry.entry_date <= date_to)
    if account_id:
        query = query.where(Entry.id.in_(select(EntryLine.entry_id).where(EntryLine.account_id == account_id)))
    if q:
        query = query.where(or_(Entry.source_ref.ilike(f"%{q.strip()}%"), Entry.description.ilike(f"%{q.strip()}%")))
    return query


def list_entries(db: Session, *, limit: int = 100, offset: int = 0, **filters) -> list[dict]:
    rows = list(
        db.scalars(
            _entries_query(**filters)
            .order_by(Entry.entry_date.desc(), Entry.id.desc())
            .limit(min(limit, 500))
            .offset(offset)
        )
    )
    return _entries_out(db, rows, with_lines=False)


def _entry(db: Session, public_id, *, all_companies: bool, company_ids, lock: bool = False) -> Entry:
    q = _entry_scope(select(Entry).where(Entry.public_id == public_id), all_companies, company_ids)
    entry = db.scalar(q.with_for_update() if lock else q)
    if entry is None:
        raise AppError(404, "entry_not_found")
    return entry


def get_entry(db: Session, public_id, **scope) -> dict:
    return _entries_out(db, [_entry(db, public_id, **scope)], with_lines=True)[0]


def _picked(
    db: Session, ids: list | None, date_from: date | None, date_to: date | None, *, generated_only: bool = False
) -> list[Entry]:
    """Drafts by id, or every draft of a period; generated_only (discarding a period's drafts to make them again)
    leaves the accountant's own entries alone: nothing would make them again."""
    q = select(Entry).where(Entry.status == "draft")
    if ids:
        q = q.where(Entry.public_id.in_(ids))
    else:
        if date_from is None or date_to is None:
            raise AppError(422, "invalid_range")
        q = q.where(Entry.entry_date.between(date_from, date_to))
        if generated_only:
            q = q.where(Entry.source_kind.not_in(("manual", "opening")))
    return list(db.scalars(q.with_for_update()))


def approve_entries(
    db: Session, *, ids=None, date_from=None, date_to=None, actor_user_id: int, all_companies: bool, **_
) -> int:
    """Drafts approved: they never change again (FR-FIN-05)."""
    _need_all_companies(all_companies)
    rows = _picked(db, ids, date_from, date_to)
    for m in sorted({e.entry_date.replace(day=1) for e in rows}):
        periods.check_open(db, m)
    now = utcnow()
    for e in rows:
        e.status, e.approved_by, e.approved_at = "approved", actor_user_id, now
    if rows:
        audit.record(
            db,
            action="finance.entries.approved",
            entity_type="entry",
            actor_user_id=actor_user_id,
            after={"numbers": sorted(e.number for e in rows)},
        )
    db.commit()
    return len(rows)


def discard_drafts(
    db: Session, *, ids=None, date_from=None, date_to=None, actor_user_id: int, all_companies: bool, **_
) -> int:
    """Drafts removed, to be made again (after the chart changed); their documents are entered at the next posting.
    A period's discard keeps manual and opening drafts (deleted one by one, delete_draft)."""
    _need_all_companies(all_companies)
    rows = _picked(db, ids, date_from, date_to, generated_only=True)
    if rows:
        numbers = sorted(e.number for e in rows)
        db.execute(delete(Entry).where(Entry.id.in_([e.id for e in rows])))
        audit.record(
            db,
            action="finance.entries.discarded",
            entity_type="entry",
            actor_user_id=actor_user_id,
            after={"numbers": numbers},
        )
    db.commit()
    return len(rows)


def reverse_entry(
    db: Session, public_id, *, reason: str, day: date | None, actor_user_id: int, all_companies: bool, **scope
) -> dict:
    """An approved entry corrected by its mirror image, approved at once; its document can then be entered again
    (with the chart as it is now, or not at all if it was cancelled)."""
    _need_all_companies(all_companies)
    entry = _entry(db, public_id, lock=True, all_companies=all_companies, **scope)
    if entry.status != "approved":
        raise AppError(409, "entry_not_approved")
    if entry.reversed_by_id is not None or entry.source_kind == "reversal":
        raise AppError(409, "entry_already_reversed")
    if entry.source_kind == "opening":
        # dated where it stood, the day before the books start: a corrected opening then replaces it from the start
        day = entry.entry_date
    else:
        # dated as the accountant says (today by default): within the books, never before what it reverses, and
        # not in the future (an entry dated ahead may be reversed up to its own date)
        day = day or today()
        _check_date(db, day)
        if day > max(today(), entry.entry_date):
            raise AppError(422, "reversal_date_future")
        if day < entry.entry_date:
            raise AppError(422, "reversal_before_entry", date=entry.entry_date.isoformat())
    periods.check_open(db, day)  # an opening's month too: a closed month takes no entry
    reversal = Entry(
        entry_date=day,
        source_kind="reversal",
        source_ref=entry.source_ref,
        company_id=entry.company_id,
        description=i18n.t(
            db, i18n.default_language(db).code, "finance_source.reversal", number=entry.number, reason=reason
        ),
        reverses_id=entry.id,
        reason=reason,
        created_by=actor_user_id,
    )
    db.add(reversal)
    db.flush()
    for ln in db.scalars(select(EntryLine).where(EntryLine.entry_id == entry.id).order_by(EntryLine.line_no)):
        db.add(
            EntryLine(
                entry_id=reversal.id,
                line_no=ln.line_no,
                account_id=ln.account_id,
                debit=ln.credit,
                credit=ln.debit,
                memo=ln.memo,
                employee_id=ln.employee_id,
            )
        )
    db.flush()
    reversal.status, reversal.approved_by, reversal.approved_at = "approved", actor_user_id, utcnow()
    db.flush()
    entry.reversed_by_id = reversal.id
    audit.record(
        db,
        action="finance.entry.reversed",
        entity_type="entry",
        entity_id=entry.public_id,
        actor_user_id=actor_user_id,
        company_id=entry.company_id,
        after={"number": entry.number, "reversal": reversal.number, "reason": reason},
    )
    db.commit()
    return _entries_out(db, [reversal], with_lines=True)[0]


def export_lines(db: Session, **filters) -> list[dict]:
    """One row per line, oldest first, for the client's accounting system (FR-FIN-04)."""
    rows = db.execute(
        select(Entry, EntryLine, Account)
        .join(EntryLine, EntryLine.entry_id == Entry.id)
        .join(Account, Account.id == EntryLine.account_id)
        .where(Entry.id.in_(_entries_query(**filters).with_only_columns(Entry.id)))
        .order_by(Entry.entry_date, Entry.number, EntryLine.line_no)
        .limit(EXPORT_MAX_LINES + 1)
    ).all()
    if len(rows) > EXPORT_MAX_LINES:
        raise AppError(422, "export_too_large", max=EXPORT_MAX_LINES)
    return [{"entry": e, "line": ln, "account": a} for e, ln, a in rows]


def trial_balance(db: Session, date_from: date, date_to: date, *, all_companies: bool, **_) -> list[dict]:
    """Each account's approved debits and credits up to the start of the period, in it, and at its end: what the
    accountant checks against his own books."""
    _need_all_companies(all_companies)
    _span(date_from, date_to, 400)
    rows = db.execute(
        select(
            Account,
            func.coalesce(func.sum(EntryLine.debit - EntryLine.credit).filter(Entry.entry_date < date_from), 0),
            func.coalesce(func.sum(EntryLine.debit).filter(Entry.entry_date >= date_from), 0),
            func.coalesce(func.sum(EntryLine.credit).filter(Entry.entry_date >= date_from), 0),
        )
        .join(EntryLine, EntryLine.account_id == Account.id)
        .join(Entry, Entry.id == EntryLine.entry_id)
        .where(Entry.status == "approved", Entry.entry_date <= date_to)
        .group_by(Account.id)
        .order_by(Account.code)
    ).all()
    return [
        {
            "account": {"id": a.id, "code": a.code, "name": a.name, "type": a.type},
            "opening": Decimal(o),
            "debit": Decimal(d),
            "credit": Decimal(c),
            "closing": Decimal(o) + Decimal(d) - Decimal(c),
        }
        for a, o, d, c in rows
    ]


def _parties(db: Session, sources: set[tuple[str, int]]) -> dict[tuple[str, int], dict]:
    """Who each entry was with, from its document: the driver whose cash moved, the employee of a deduction or an
    expense, the maintenance center of an invoice, the supplier written on an expense. Payroll runs have none."""
    from app.modules.cash import service as cash
    from app.modules.fines import service as fines
    from app.modules.maintenance import service as maintenance
    from app.modules.payroll import service as payroll

    by_kind: dict[str, set[int]] = defaultdict(set)
    for kind, source_id in sources:
        by_kind[kind].add(source_id)
    employees: dict[tuple[str, int], int] = {}
    out: dict[tuple[str, int], dict] = {}
    for j, d in cash.journal_drivers(db, by_kind["cash_journal"]).items():
        employees[("cash_journal", j)] = d
    for f, d in fines.fine_drivers(db, by_kind["fine_payment"]).items():
        employees[("fine_payment", f)] = d
    for x, e in payroll.deduction_employees(db, by_kind["deduction"]).items():
        employees[("deduction", x)] = e
    for kind in ("maintenance_invoice", "invoice_payment"):
        for i, center in maintenance.invoice_centers(db, by_kind[kind]).items():
            out[(kind, i)] = center
    expense_ids = by_kind["expense"] | by_kind["expense_payment"]
    if expense_ids:
        centers = {}
        rows = db.execute(
            select(Expense.id, Expense.employee_id, Expense.center_id, Expense.supplier).where(
                Expense.id.in_(expense_ids)
            )
        ).all()
        if any(c for _, _, c, _ in rows):
            centers = maintenance.center_names(db, {c for _, _, c, _ in rows if c})
        for x, employee_id, center_id, supplier in rows:
            for kind in ("expense", "expense_payment"):
                if (kind, x) not in sources:
                    continue
                if employee_id:
                    employees[(kind, x)] = employee_id
                elif center_id and center_id in centers:
                    out[(kind, x)] = centers[center_id]
                elif supplier:
                    out[(kind, x)] = {"type": "supplier", "id": None, "name": {"ar": supplier, "en": supplier}}
    names = people.names(db, set(employees.values()))
    for key, employee_id in employees.items():
        if employee_id in names:
            out[key] = {"type": "employee", "id": names[employee_id]["id"], "name": names[employee_id]["name"]}
    return out


LEDGER_LINES = 2000


def ledger(db: Session, account_id: int, date_from: date, date_to: date, *, all_companies: bool, **_) -> dict:
    """An account's statement (approved entries): its balance before the period, each line in it with whom it was
    with and the running balance, and what each party (driver, employee, center, supplier) holds on it up to the end:
    the trial balance's row opened to show what happened and with whom."""
    _need_all_companies(all_companies)
    _span(date_from, date_to, 400)
    account = db.get(Account, account_id)
    if account is None:
        raise AppError(404, "account_not_found")
    rows = db.execute(
        select(Entry, EntryLine.debit, EntryLine.credit, EntryLine.employee_id)
        .join(EntryLine, EntryLine.entry_id == Entry.id)
        .where(EntryLine.account_id == account_id, Entry.status == "approved", Entry.entry_date <= date_to)
        .order_by(Entry.entry_date, Entry.number, EntryLine.line_no)
    ).all()
    # a reversal is with whoever the entry it reverses was with
    reversed_ids = {e.reverses_id for e, *_ in rows if e.reverses_id}
    origins = {
        i: (k, s)
        for i, k, s in db.execute(
            select(Entry.id, Entry.source_kind, Entry.source_id).where(Entry.id.in_(reversed_ids))
        )
    }

    def source(e: Entry) -> tuple[str, int] | None:
        found = origins.get(e.reverses_id) if e.reverses_id else (e.source_kind, e.source_id)
        return None if found is None or found[1] is None else found

    parties = _parties(db, {s for e, *_ in rows if (s := source(e)) is not None})
    # a line that names its employee (a manual or opening line) is with him, before its document says anything
    named = people.names(db, {emp for *_, emp in rows if emp})
    opening = ZERO
    lines, holders = [], {}
    period_debit = period_credit = ZERO
    for e, debit, credit, employee_id in rows:
        if employee_id in named:
            party = {"type": "employee", "id": named[employee_id]["id"], "name": named[employee_id]["name"]}
        else:
            party = parties.get(source(e))
        if party is not None:
            key = (party["type"], party["id"] or party["name"]["ar"])
            h = holders.setdefault(key, {"party": party, "debit": ZERO, "credit": ZERO})
            h["debit"] += debit
            h["credit"] += credit
        if e.entry_date < date_from:
            opening += debit - credit
            continue
        period_debit += debit
        period_credit += credit
        if len(lines) < LEDGER_LINES:
            lines.append(
                {
                    "entry_id": e.public_id,
                    "number": e.number,
                    "date": e.entry_date,
                    "ref": e.source_ref,
                    "description": e.description,
                    "reversal": e.reverses_id is not None,
                    "party": party,
                    "debit": debit,
                    "credit": credit,
                }
            )
    balance = opening
    for ln in lines:
        balance += ln["debit"] - ln["credit"]
        ln["balance"] = balance
    held = sorted(holders.values(), key=lambda h: -abs(h["debit"] - h["credit"]))
    return {
        "account": {"id": account.id, "code": account.code, "name": account.name, "type": account.type},
        "opening": opening,
        "debit": period_debit,
        "credit": period_credit,
        "closing": opening + period_debit - period_credit,
        "lines": lines,
        "truncated": len(lines) == LEDGER_LINES,
        "parties": [{**h, "balance": h["debit"] - h["credit"]} for h in held if h["debit"] != h["credit"]],
    }


def auto_post(db: Session) -> dict:
    """The daily posting (beat): the last 45 days, so a document approved late is entered too."""
    last = today()
    return post(db, last - timedelta(days=44), last, actor_user_id=None, all_companies=True)


# ------------------------------------------------------------------ the accountant's own entries: manual and opening

MANUAL_MAX_LINES = 200


def _lines(db: Session, raw: list[dict], *, scope: dict) -> list[dict]:
    """The lines as written: each on an open account, one side only; the employee named by his public id."""
    ids = {ln["account_id"] for ln in raw}
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(ids)))}
    out = []
    for ln in raw:
        account = accounts.get(ln["account_id"])
        if account is None:
            raise AppError(404, "account_not_found")
        if not account.active:
            raise AppError(422, "account_inactive", code=account.code)
        debit, credit = Decimal(ln.get("debit") or 0), Decimal(ln.get("credit") or 0)
        if debit < 0 or credit < 0 or (debit > 0) == (credit > 0):
            raise AppError(422, "line_one_side", code=account.code)
        employee = ln.get("employee_id")
        if employee is not None and not isinstance(employee, int):
            employee = people.ref_by_public_id(db, employee, **scope).id
        out.append(
            {"account": account, "debit": debit, "credit": credit, "memo": ln.get("memo"), "employee_id": employee}
        )
    return out


def _difference(lines: list[dict]) -> Decimal:
    return sum((ln["debit"] - ln["credit"] for ln in lines), ZERO)


def _check_company(db: Session, company_id: int | None) -> None:
    if company_id is not None and not org.company_ids_exist(db, [company_id]):
        raise AppError(404, "company_not_found")


def _write(
    db: Session,
    *,
    kind: str,
    day: date,
    ref: str,
    description: str,
    company_id: int | None,
    lines: list[dict],
    actor_user_id: int,
) -> Entry:
    """A manual or opening entry with its lines, as a draft; ref "MAN" / "OPEN" takes the entry's number."""
    number = db.scalar(ENTRY_SEQ.next_value())
    entry = Entry(
        number=number,
        entry_date=day,
        source_kind=kind,
        source_ref=ref if ref.startswith("OLD-") else f"{ref}-{number}",
        company_id=company_id,
        description=description,
        created_by=actor_user_id,
    )
    db.add(entry)
    db.flush()
    for n, ln in enumerate(lines, start=1):
        db.add(
            EntryLine(
                entry_id=entry.id,
                line_no=n,
                account_id=ln["account"].id,
                debit=ln["debit"],
                credit=ln["credit"],
                memo=ln.get("memo"),
                employee_id=ln.get("employee_id"),
            )
        )
    return entry


def create_manual(
    db: Session, data: dict, *, actor_user_id: int, all_companies: bool, company_ids, commit: bool = True
) -> dict:
    """A balanced entry the accountant writes himself (an accrual, a correction after a reversal...): a draft for
    finance.approve, or approved at once when entries are approved automatically (settings finance)."""
    _need_all_companies(all_companies)
    scope = {"all_companies": all_companies, "company_ids": company_ids}
    _check_company(db, data.get("company_id"))
    _check_date(db, data["entry_date"])
    periods.check_open(db, data["entry_date"])
    lines = _lines(db, data["lines"], scope=scope)
    if not 2 <= len(lines) <= MANUAL_MAX_LINES:
        raise AppError(422, "entry_lines_count", min=2, max=MANUAL_MAX_LINES)
    difference = _difference(lines)
    if difference:
        raise AppError(422, "entry_unbalanced", difference=f"{difference:.3f}")
    entry = _write(
        db,
        kind="manual",
        day=data["entry_date"],
        ref=data.get("ref") or "MAN",
        description=data["description"],
        company_id=data.get("company_id"),
        lines=lines,
        actor_user_id=actor_user_id,
    )
    audit.record(
        db,
        action="finance.entry.manual",
        entity_type="entry",
        entity_id=entry.public_id,
        actor_user_id=actor_user_id,
        company_id=entry.company_id,
        after={"number": entry.number, "ref": entry.source_ref, "date": entry.entry_date, "lines": len(lines)},
    )
    if _auto(db):
        _approve_by_system(db, [entry])
    if not commit:
        return {"entry": entry}
    db.commit()
    return _entries_out(db, [entry], with_lines=True)[0]


def _opening_lock(db: Session) -> None:
    """One opening at a time: the check for an existing one and the new one are then never interleaved."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('finance.opening'))"))


def opening_exists(db: Session, company_id: int | None) -> bool:
    same = Entry.company_id.is_(None) if company_id is None else Entry.company_id == company_id
    return (
        db.scalar(select(Entry.id).where(Entry.source_kind == "opening", Entry.reversed_by_id.is_(None), same).limit(1))
        is not None
    )


def create_opening(
    db: Session, data: dict, *, actor_user_id: int, all_companies: bool, company_ids, commit: bool = True
) -> dict:
    """The books' opening balances, dated the day before they start: the lines as given, and what does not balance
    on the opening balances account (role opening_equity) as one line, said in the answer. Once per company (or once
    for the books without a company) unless the earlier one is reversed (or a draft deleted)."""
    _need_all_companies(all_companies)
    scope = {"all_companies": all_companies, "company_ids": company_ids}
    start = books(db).books_start_date
    if start is None:
        raise AppError(422, "books_start_required")
    company_id = data.get("company_id")
    _check_company(db, company_id)
    periods.check_open(db, start - timedelta(days=1))
    _opening_lock(db)
    if opening_exists(db, company_id):
        raise AppError(409, "opening_exists")
    lines = _lines(db, data["lines"], scope=scope)
    if not lines:
        raise AppError(422, "entry_lines_count", min=1, max=MANUAL_MAX_LINES)
    difference = _difference(lines)  # debits over credits
    equity = posting.role_accounts(db).get("opening_equity")
    if difference:
        if equity is None:
            raise AppError(422, "account_role_missing", role="opening_equity")
        if not equity.active:
            raise AppError(422, "account_inactive", code=equity.code)
        lines.append(
            {
                "account": equity,
                "debit": -difference if difference < 0 else ZERO,
                "credit": difference if difference > 0 else ZERO,
                "memo": None,
                "employee_id": None,
            }
        )
    lang = i18n.default_language(db).code
    entry = _write(
        db,
        kind="opening",
        day=start - timedelta(days=1),
        ref="OPEN",
        description=" ".join(i18n.t(db, lang, "finance_source.opening", date=start.isoformat()).split()),
        company_id=company_id,
        lines=lines,
        actor_user_id=actor_user_id,
    )
    audit.record(
        db,
        action="finance.entry.opening",
        entity_type="entry",
        entity_id=entry.public_id,
        actor_user_id=actor_user_id,
        company_id=company_id,
        after={"number": entry.number, "lines": len(lines), "difference": difference},
    )
    if _auto(db):
        _approve_by_system(db, [entry])
    out = {
        "difference": difference,
        "equity_account": {"id": equity.id, "code": equity.code, "name": equity.name} if equity else None,
    }
    if not commit:
        return out | {"entry": entry}
    db.commit()
    return out | {"entry": _entries_out(db, [entry], with_lines=True)[0]}


def delete_draft(db: Session, public_id, *, actor_user_id: int, all_companies: bool, **scope) -> None:
    """A manual or opening draft removed (a generated one is discarded with its period, to be made again)."""
    _need_all_companies(all_companies)
    entry = _entry(db, public_id, lock=True, all_companies=all_companies, **scope)
    if entry.status != "draft" or entry.source_kind not in ("manual", "opening"):
        raise AppError(409, "entry_not_deletable")
    number = entry.number
    db.execute(delete(Entry).where(Entry.id == entry.id))
    audit.record(
        db,
        action="finance.entries.discarded",
        entity_type="entry",
        entity_id=public_id,
        actor_user_id=actor_user_id,
        after={"numbers": [number]},
    )
    db.commit()


# ------------------------------------------------------------------ an old system's books, from Excel


def import_template() -> bytes:
    from app.modules.finance import oldbooks

    return oldbooks.template()


def import_books(
    db: Session,
    data: bytes,
    *,
    apply: bool,
    company_id: int | None,
    actor_user_id: int,
    all_companies: bool,
    company_ids,
) -> dict:
    """The old system's opening balances and entries, checked (apply=false changes nothing) or imported all at once
    in one transaction (apply=true, only without errors): one opening entry (the difference to opening balances) and
    one manual entry per old entry number, referenced OLD-<number>, approved as the settings say."""
    from app.modules.finance import oldbooks

    _need_all_companies(all_companies)
    _check_company(db, company_id)
    scope = {"all_companies": all_companies, "company_ids": company_ids}
    start = books(db).books_start_date
    accounts = {a.code: a for a in db.scalars(select(Account))}
    found = oldbooks.read(data)
    result = oldbooks.check(found, accounts=accounts, books_start=start, civil_ids=_civil_ids(db, found))
    if found.opening:
        if start is None:
            result.error(oldbooks.OPENING, None, "books_start_required")
        elif opening_exists(db, company_id):
            result.error(oldbooks.OPENING, None, "opening_exists")
    numbers = sorted(result.entries)
    taken = sorted(
        r[4:]
        for r in db.scalars(
            select(Entry.source_ref).where(
                Entry.source_kind == "manual",
                Entry.reversed_by_id.is_(None),
                Entry.source_ref.in_([f"OLD-{n}" for n in numbers]),
            )
        )
    )
    if taken and apply:
        raise AppError(409, "old_entries_imported", numbers=", ".join(taken))
    for n in taken:
        result.error(oldbooks.ENTRIES, result.entries[n]["row"], "old_entry_imported", number=n)
    for n in numbers:  # a closed month takes no entry
        day = result.entries[n]["date"]
        if periods.is_closed(db, day):
            result.error(oldbooks.ENTRIES, result.entries[n]["row"], "period_closed", month=f"{day:%Y-%m}")
    if found.opening and start is not None and periods.is_closed(db, start - timedelta(days=1)):
        result.error(oldbooks.OPENING, None, "period_closed", month=f"{start - timedelta(days=1):%Y-%m}")
    out = result.summary()
    if not apply or result.errors:
        return out | {"applied": False, "numbers": []}

    made: list[int] = []
    lang = i18n.default_language(db).code
    if result.opening:
        _opening_lock(db)
        opened = create_opening(
            db,
            {"company_id": company_id, "lines": result.opening},
            actor_user_id=actor_user_id,
            commit=False,
            **scope,
        )
        made.append(opened["entry"].number)
    for n in numbers:
        old = result.entries[n]
        made_entry = create_manual(
            db,
            {
                "entry_date": old["date"],
                "description": old["description"] or i18n.t(db, lang, "finance_source.imported", number=n),
                "company_id": company_id,
                "lines": old["lines"],
                "ref": f"OLD-{n}",
            },
            actor_user_id=actor_user_id,
            commit=False,
            **scope,
        )
        made.append(made_entry["entry"].number)
    audit.record(
        db,
        action="finance.books.imported",
        entity_type="entry",
        actor_user_id=actor_user_id,
        company_id=company_id,
        after={"opening": bool(result.opening), "entries": len(numbers), "numbers": made},
    )
    db.commit()
    return out | {"applied": True, "numbers": made}


def _civil_ids(db: Session, found) -> dict[str, int]:
    """The employees the file names by civil ID: those found (the others are a warning)."""
    out = {}
    for civil_id in found.civil_ids():
        ref = people.find(db, civil_id=civil_id, phone=None)
        if ref is not None:
            out[civil_id] = ref.id
    return out


# ------------------------------------------------------------------ month close


def list_periods(db: Session, first: date, last: date, *, all_companies: bool, **_) -> list[dict]:
    _need_all_companies(all_companies)
    return periods.list_periods(db, first.replace(day=1), last.replace(day=1))


def check_period(db: Session, month: str, *, all_companies: bool, **_) -> dict:
    """The month's checklist: what is left to do before it can close (nothing: ready)."""
    _need_all_companies(all_companies)
    return periods.check(db, periods.parse_month(month))


def close_period(db: Session, month: str, *, actor_user_id: int, all_companies: bool, **_) -> dict:
    _need_all_companies(all_companies)
    return periods.close(db, periods.parse_month(month), actor_user_id=actor_user_id)


def reopen_period(db: Session, month: str, *, reason: str, actor_user_id: int, all_companies: bool, **_) -> dict:
    _need_all_companies(all_companies)
    return periods.reopen(db, periods.parse_month(month), reason=reason, actor_user_id=actor_user_id)
