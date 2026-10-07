"""Finance (BRD FR-FIN-01..05): the chart of accounts and its roles, expense types, expenses with their files and
payment, and the journal entries made from the system's documents (app.modules.finance.posting): made as drafts,
approved by the accountant, never changed once approved (a reversing entry corrects one), exported to Excel."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.finance import posting
from app.modules.finance.models import Account, AccountRole, Entry, EntryLine, Expense, ExpenseFile, ExpenseType
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
    employees = people.names(db, {e.employee_id for e in rows if e.employee_id})
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
                "type": {"id": t.id, "code": t.code, "name": t.name},
                "expense_date": e.expense_date,
                "amount": e.amount,
                "quantity": e.quantity,
                "payment_method": e.payment_method,
                "supplier": e.supplier,
                "reference_no": e.reference_no,
                "vehicle": {"id": vehicle["id"], "plate_number": vehicle["plate_number"]} if vehicle else None,
                "employee": employees.get(e.employee_id),
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
    expense = Expense(
        company_id=company_id,
        type_id=t.id,
        expense_date=data["expense_date"],
        amount=data["amount"],
        quantity=data.get("quantity"),
        payment_method=data["payment_method"],
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


def _approval(expense: Expense) -> dict:
    return {
        "document_id": expense.id,
        "document_key": expense.public_id,
        "document_ref": f"EXP-{expense.number}",
        "company_id": expense.company_id,
        "amount": expense.amount,
    }


def decide_expense(db: Session, public_id, *, approve: bool, note: str | None, actor_user_id: int, **scope) -> dict:
    expense = _get(db, public_id, lock=True, **scope)
    if expense.status != "pending":
        raise AppError(409, "expense_not_pending", status=expense.status)
    if not approve and not note:
        raise AppError(422, "reason_required")
    if not approvals.gate(
        db, "expense", **_approval(expense), actor_user_id=actor_user_id, approve=approve, reason=note
    ):
        db.commit()  # this step recorded; the expense waits for the next one
        return _expense_out(db, [expense])[0]
    expense.status = "approved" if approve else "rejected"
    expense.decided_by, expense.decided_at, expense.decision_note = actor_user_id, utcnow(), note
    expense.version += 1
    _audit(db, expense.status, expense, actor_user_id=actor_user_id, after={"note": note})
    db.commit()
    return _expense_out(db, [expense])[0]


def cancel_expense(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """A wrong entry, before or after approval (not once paid later): its journal entry, if made, is then listed to
    be reversed."""
    expense = _get(db, public_id, lock=True, **scope)
    if expense.status not in ("pending", "approved") or expense.paid_at is not None:
        raise AppError(409, "expense_not_cancellable", status=expense.status)
    expense.status, expense.cancel_reason = "cancelled", reason  # an approved one keeps who approved it, and when
    expense.version += 1
    approvals.withdrawn(db, "expense", [expense.id])
    _audit(db, "cancelled", expense, actor_user_id=actor_user_id, after={"reason": reason})
    db.commit()
    return _expense_out(db, [expense])[0]


def pay_expense(
    db: Session, public_id, *, paid_from: str, payment_ref: str | None, actor_user_id: int, **scope
) -> dict:
    """A supplier's invoice entered to be paid later, paid now from the treasury or the bank."""
    expense = _get(db, public_id, lock=True, **scope)
    if expense.payment_method != "payable" or expense.status != "approved" or expense.paid_at is not None:
        raise AppError(409, "expense_not_payable")
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
    docs = posting.documents(db, first, last)
    live = {
        (e.source_kind, e.source_id): e
        for e in db.scalars(
            select(Entry).where(
                Entry.source_kind != "reversal",
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
    roles = posting.role_accounts(db)
    created: dict[str, int] = defaultdict(int)
    stale, errors, seen = [], [], set()
    for doc in docs:
        key = (doc.kind, doc.id)
        seen.add(key)
        entry = live.get(key)
        if entry is not None:
            if totals.get(entry.id, ZERO) != doc.total:
                stale.append(_stale(entry, totals.get(entry.id, ZERO), doc.total))
            continue
        if doc.total == ZERO:
            continue
        try:
            with db.begin_nested():
                posting.write(db, doc, description=_describe(db, doc), roles=roles, actor_user_id=actor_user_id)
            created[doc.kind] += 1
        except AppError as e:
            errors.append({"source_ref": doc.ref, "code": e.code, "params": e.params})
    for key, entry in live.items():
        if key not in seen and first <= entry.entry_date <= last:
            stale.append(_stale(entry, totals.get(entry.id, ZERO), ZERO))
    if created:
        audit.record(
            db,
            action="finance.entries.posted",
            entity_type="entry",
            actor_user_id=actor_user_id,
            after={"from": first, "to": last, "created": dict(created)},
        )
    db.commit()
    return {"created": sum(created.values()), "by_kind": dict(created), "stale": stale, "errors": errors}


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
        for ln, a in db.execute(
            select(EntryLine, Account)
            .join(Account, Account.id == EntryLine.account_id)
            .where(EntryLine.entry_id.in_(ids))
            .order_by(EntryLine.entry_id, EntryLine.line_no)
        ):
            sums[ln.entry_id] += ln.debit
            lines[ln.entry_id].append(
                {"account": {"id": a.id, "code": a.code, "name": a.name}, "debit": ln.debit, "credit": ln.credit}
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


def _picked(db: Session, ids: list | None, date_from: date | None, date_to: date | None) -> list[Entry]:
    q = select(Entry).where(Entry.status == "draft")
    if ids:
        q = q.where(Entry.public_id.in_(ids))
    else:
        if date_from is None or date_to is None:
            raise AppError(422, "invalid_range")
        q = q.where(Entry.entry_date.between(date_from, date_to))
    return list(db.scalars(q.with_for_update()))


def approve_entries(
    db: Session, *, ids=None, date_from=None, date_to=None, actor_user_id: int, all_companies: bool, **_
) -> int:
    """Drafts approved: they never change again (FR-FIN-05)."""
    _need_all_companies(all_companies)
    rows = _picked(db, ids, date_from, date_to)
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
    """Drafts removed, to be made again (after the chart changed); their documents are entered at the next posting."""
    _need_all_companies(all_companies)
    rows = _picked(db, ids, date_from, date_to)
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
    reversal = Entry(
        entry_date=day or today(),
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
                entry_id=reversal.id, line_no=ln.line_no, account_id=ln.account_id, debit=ln.credit, credit=ln.debit
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


def auto_post(db: Session) -> dict:
    """The daily posting (beat): the last 45 days, so a document approved late is entered too."""
    last = today()
    return post(db, last - timedelta(days=44), last, actor_user_id=None, all_companies=True)
