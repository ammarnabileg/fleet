"""The chart of accounts, which account each posting uses (account roles) and the expense types in a transfer file.
An account is known by its code; a role and an expense type name their account by its code."""

from sqlalchemy import select

from app.core.errors import AppError
from app.core.transfer import CREATED, UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, each, same
from app.modules.audit import service as audit
from app.modules.finance import posting
from app.modules.finance.models import Account, AccountRole, EntryLine, ExpenseType
from app.modules.finance.schemas import AccountIn, ExpenseTypeIn
from app.modules.i18n import service as i18n


def _export_accounts(ctx: ExportContext) -> dict:
    db = ctx.db
    rows = list(db.scalars(select(Account).order_by(Account.code)))
    codes = {a.id: a.code for a in rows}
    roles = dict(db.execute(select(AccountRole.role, AccountRole.account_id)).tuples().all())
    return {
        "accounts": [{"code": a.code, "name": a.name, "type": a.type, "active": a.active} for a in rows],
        "roles": {r: codes[a] for r, a in sorted(roles.items()) if a in codes},
    }


def _apply_accounts(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db
    if not isinstance(data, dict):
        report.skip("*", "config_section_invalid")
        return

    def one(item):
        clean = AccountIn.model_validate({k: item.get(k) for k in ("code", "name", "type")}).model_dump()
        clean["name"] = i18n.validate_localized(db, clean["name"])
        active = bool(item.get("active", True))
        a = db.scalar(select(Account).where(Account.code == clean["code"]).with_for_update())
        if a is None:
            db.add(Account(**clean, active=active))
            db.flush()
            return CREATED
        if same(a.name, clean["name"]) and a.type == clean["type"] and a.active == active:
            return UNCHANGED
        if a.type != clean["type"] and db.scalar(select(EntryLine.account_id).where(EntryLine.account_id == a.id)):
            raise AppError(409, "account_in_use")
        if not active and a.active:
            pointed = db.scalar(select(AccountRole.role).where(AccountRole.account_id == a.id).limit(1))
            typed = db.scalar(select(ExpenseType.code).where(ExpenseType.account_id == a.id, ExpenseType.active))
            if pointed or typed:
                raise AppError(409, "account_in_role", role=pointed or typed)
        a.name, a.type, a.active = clean["name"], clean["type"], active
        a.version += 1
        db.flush()
        return UPDATED

    each(db, report, data.get("accounts") or [], lambda i: i.get("code"), one)

    def role(item):
        name, code = item
        if name not in posting.ROLES:
            raise AppError(422, "unknown_account_role", role=name)
        account = db.scalar(select(Account).where(Account.code == code))
        if account is None:
            raise AppError(422, "config_account_missing", code=code)
        if not account.active:
            raise AppError(422, "account_inactive", code=code)
        row = db.get(AccountRole, name, with_for_update=True)
        if row is not None and row.account_id == account.id:
            return UNCHANGED
        if row is None:
            db.add(AccountRole(role=name, account_id=account.id))
        else:
            row.account_id = account.id
        db.flush()
        return CREATED if row is None else UPDATED

    sub = Report()
    roles = data.get("roles") or {}
    each(db, sub, sorted(roles.items()) if isinstance(roles, dict) else roles, lambda i: f"role:{i[0]}", role)
    report.created += sub.created
    report.updated += sub.updated
    report.unchanged += sub.unchanged
    report.skipped += sub.skipped
    if report.changed:
        audit.record(
            db,
            action="finance.roles.updated",
            entity_type="account",
            actor_user_id=ctx.actor_user_id,
            after={"import": report.out() | {"skipped": len(report.skipped)}},
            comment="config import",
        )


def _export_types(ctx: ExportContext) -> list[dict]:
    db = ctx.db
    codes = dict(db.execute(select(Account.id, Account.code)).tuples().all())
    rows = db.scalars(select(ExpenseType).order_by(ExpenseType.sort_order, ExpenseType.code))
    return [
        {
            "code": t.code,
            "name": t.name,
            "account": codes.get(t.account_id),
            "active": t.active,
            "sort_order": t.sort_order,
            "petty": t.petty,
        }
        for t in rows
    ]


def _apply_types(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        account = db.scalar(select(Account).where(Account.code == item.get("account")))
        if account is None:
            raise AppError(422, "config_account_missing", code=item.get("account"))
        fields = {k: item.get(k) for k in ("code", "name", "sort_order", "petty") if k in item}
        clean = ExpenseTypeIn.model_validate(fields | {"account_id": account.id}).model_dump()
        clean["name"] = i18n.validate_localized(db, clean["name"])
        clean["active"] = bool(item.get("active", True))
        t = db.scalar(select(ExpenseType).where(ExpenseType.code == clean["code"]).with_for_update())
        if t is None:
            db.add(ExpenseType(**clean))
            db.flush()
            return CREATED
        values = {k: v for k, v in clean.items() if k != "code"}
        if all(same(getattr(t, k), v) for k, v in values.items()):
            return UNCHANGED
        for k, v in values.items():
            setattr(t, k, v)
        db.flush()
        return UPDATED

    each(db, report, data, lambda i: i.get("code"), one)


SECTIONS_OUT = [
    Section(
        "accounts",
        {"ar": "دليل الحسابات وربط الحسابات", "en": "Chart of accounts and account roles"},
        _export_accounts,
        _apply_accounts,
        order=40,
    ),
    Section("expense_types", {"ar": "أنواع المصروفات", "en": "Expense types"}, _export_types, _apply_types, order=41),
]
