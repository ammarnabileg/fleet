"""How each document becomes a journal entry (BRD FR-FIN-03). The lines name roles ("treasury", "salaries_payable"...)
that the chart maps to the accountant's accounts, except an expense's own account (its type's). These are defaults
for the client's accountant to confirm: what a role means is his decision, the system only applies it.

    cash journal          its own lines, each cash account's kind to its role (balanced already)
    expense               Dr its type's account / Cr treasury, bank, or suppliers payable (paid later)
    expense payment       Dr suppliers payable / Cr treasury or bank
    maintenance invoice   Dr maintenance expense / Cr suppliers payable
    invoice payment       Dr suppliers payable / Cr bank
    payroll run           Dr salaries expense (net + installments) / Cr salaries payable (net),
                          Cr employee receivables (installments recovered)
    payroll payment       Dr salaries payable / Cr bank
    deduction             Dr employee receivables / Cr the deduction's source (accident damage recovered...)
    fine payment          Dr traffic fines expense / Cr bank
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.finance.models import Account, AccountRole, Entry, EntryLine, Expense, ExpenseType

ZERO = Decimal("0.000")
ROLES = (
    "treasury",
    "bank",
    "driver_cash",
    "employee_receivable",
    "payroll_recovery",
    "deduction_advance",
    "cod_clearing",
    "suppliers_payable",
    "salaries_payable",
    "opening_equity",
    "deduction_accident",
    "deduction_fine",
    "deduction_sim",
    "deduction_other",
    "cash_adjustments",
    "driver_salaries_expense",
    "salaries_expense",
    "maintenance_expense",
    "traffic_fines_expense",
    "cash_writeoff",
    "fuel_expense",
)
CASH_ROLE = {
    "driver": "driver_cash",
    "treasury": "treasury",
    "bank": "bank",
    "cod_clearing": "cod_clearing",
    "adjustments": "cash_adjustments",
    "payroll_recovery": "payroll_recovery",
    "writeoff": "cash_writeoff",
    "opening": "opening_equity",
    "fuel": "fuel_expense",
}
PAID_FROM = {"treasury": "treasury", "bank": "bank", "payable": "suppliers_payable"}


@dataclass
class Doc:
    """A document to enter: its lines name a role (str) or an account id (int), debit or credit."""

    kind: str
    id: int
    day: date
    ref: str
    company_id: int | None
    text: str  # the catalog key under finance_source, for the description
    params: dict = field(default_factory=dict)
    lines: list[tuple[str | int, Decimal, Decimal]] = field(default_factory=list)

    def debit(self, target: str | int, amount: Decimal) -> "Doc":
        if amount:
            self.lines.append((target, Decimal(amount), ZERO))
        return self

    def credit(self, target: str | int, amount: Decimal) -> "Doc":
        if amount:
            self.lines.append((target, ZERO, Decimal(amount)))
        return self

    @property
    def total(self) -> Decimal:
        return sum((d for _, d, _ in self.lines), ZERO)


def documents(db: Session, first: date, last: date) -> list[Doc]:
    """Every document of first..last that makes an entry, in each module's terms turned into lines."""
    from app.modules.cash import service as cash
    from app.modules.fines import service as fines
    from app.modules.maintenance import service as maintenance
    from app.modules.payroll import service as payroll
    from app.modules.people import service as people

    docs: list[Doc] = []
    journals = cash.posted_journals(db, first, last)
    owners = people.company_ids_of(db, {ln["driver_id"] for j in journals for ln in j["lines"] if ln["driver_id"]})
    for j in journals:
        driver = next((ln["driver_id"] for ln in j["lines"] if ln["driver_id"]), None)
        doc = Doc(
            "cash_journal",
            j["id"],
            j["date"],
            f"CASH-{j['public_id'][:8]}",
            owners.get(driver),
            "cash_journal",
            {"kind": j["kind"], "reason": j["reason"] or ""},
        )
        for ln in j["lines"]:
            role = CASH_ROLE[ln["kind"]]
            doc.debit(role, ln["amount"]) if ln["amount"] > 0 else doc.credit(role, -ln["amount"])
        docs.append(doc)

    for e, type_name, account_id in db.execute(
        select(Expense, ExpenseType.name, ExpenseType.account_id)
        .join(ExpenseType, ExpenseType.id == Expense.type_id)
        .where(Expense.status == "approved", Expense.expense_date.between(first, last))
    ):
        docs.append(
            Doc(
                "expense",
                e.id,
                e.expense_date,
                f"EXP-{e.number}",
                e.company_id,
                "expense",
                _expense_params(e, type_name),
            )
            .debit(account_id, e.amount)
            .credit(PAID_FROM[e.payment_method], e.amount)
        )
    paid_on = func.date(func.timezone("Asia/Kuwait", Expense.paid_at))
    for e, type_name, day in db.execute(
        select(Expense, ExpenseType.name, paid_on)
        .join(ExpenseType, ExpenseType.id == Expense.type_id)
        .where(Expense.paid_at.is_not(None), paid_on.between(first, last))
    ):
        docs.append(
            Doc(
                "expense_payment",
                e.id,
                day,
                f"EXP-{e.number}",
                e.company_id,
                "expense_payment",
                _expense_params(e, type_name),
            )
            .debit("suppliers_payable", e.amount)
            .credit(PAID_FROM[e.paid_from], e.amount)
        )

    invoices = maintenance.invoices_for_posting(db, first, last)
    for i in invoices["approved"]:
        docs.append(
            Doc(
                "maintenance_invoice",
                i["id"],
                i["date"],
                f"INV-{i['number']}",
                i["company_id"],
                "maintenance_invoice",
                {"number": i["number"], "center": i["center"]},
            )
            .debit("maintenance_expense", i["total"])
            .credit("suppliers_payable", i["total"])
        )
    for i in invoices["paid"]:
        docs.append(
            Doc(
                "invoice_payment",
                i["id"],
                i["date"],
                f"INV-{i['number']}",
                i["company_id"],
                "invoice_payment",
                {"number": i["number"], "center": i["center"], "ref": i["payment_ref"] or ""},
            )
            .debit("suppliers_payable", i["total"])
            .credit("bank", i["total"])
        )

    runs = payroll.runs_for_posting(db, first, last)
    for r in runs["approved"]:
        docs.append(
            Doc(
                "payroll_run",
                r["id"],
                r["date"],
                f"PAY-{r['month']:%Y-%m}-{r['company_id']}",
                r["company_id"],
                "payroll_run",
                {"month": f"{r['month']:%Y-%m}"},
            )
            .debit("driver_salaries_expense", r["drivers"])
            .debit("salaries_expense", r["net"] + r["installments"] - r["drivers"])
            .credit("salaries_payable", r["net"])
            .credit("employee_receivable", r["installments"])
        )
    for r in runs["paid"]:
        docs.append(
            Doc(
                "payroll_payment",
                r["id"],
                r["date"],
                f"PAY-{r['month']:%Y-%m}-{r['company_id']}",
                r["company_id"],
                "payroll_payment",
                {"month": f"{r['month']:%Y-%m}", "ref": r["payment_ref"] or ""},
            )
            .debit("salaries_payable", r["net"])
            .credit("bank", r["net"])
        )

    for d in payroll.deductions_for_posting(db, first, last):
        docs.append(
            Doc(
                "deduction",
                d["id"],
                d["date"],
                f"DED-{d['id']}",
                d["company_id"],
                "deduction",
                {"source": d["source_type"], "reason": d["reason"]},
            )
            .debit("employee_receivable", d["amount"])
            .credit(f"deduction_{d['source_type']}", d["amount"])
        )

    for f in fines.paid_for_posting(db, first, last):
        docs.append(
            Doc(
                "fine_payment",
                f["id"],
                f["date"],
                f"FINE-{f['number']}",
                f["company_id"],
                "fine_payment",
                {"number": f["number"], "violation": f["violation"], "ref": f["payment_ref"] or ""},
            )
            .debit("traffic_fines_expense", f["amount"])
            .credit("bank", f["amount"])
        )
    return docs


def _expense_params(e: Expense, type_name: dict) -> dict:
    return {"number": e.number, "type": type_name, "supplier": e.supplier or ""}


def role_accounts(db: Session) -> dict[str, Account]:
    return {
        role: account
        for role, account in db.execute(
            select(AccountRole.role, Account).join(Account, Account.id == AccountRole.account_id)
        )
    }


def write(db: Session, doc: Doc, *, description: str, roles: dict[str, Account], actor_user_id: int | None) -> Entry:
    """The document's draft entry; 422 if a role has no account, or its account is closed."""
    accounts = {
        a.id: a
        for a in db.scalars(select(Account).where(Account.id.in_([t for t, *_ in doc.lines if isinstance(t, int)])))
    }
    entry = Entry(
        entry_date=doc.day,
        source_kind=doc.kind,
        source_id=doc.id,
        source_ref=doc.ref,
        company_id=doc.company_id,
        description=description,
        created_by=actor_user_id,
    )
    db.add(entry)
    db.flush()
    for n, (target, debit, credit) in enumerate(doc.lines, start=1):
        account = accounts.get(target) if isinstance(target, int) else roles.get(target)
        if account is None:
            raise AppError(422, "account_role_missing", role=str(target))
        if not account.active:
            raise AppError(422, "account_inactive", code=account.code)
        db.add(EntryLine(entry_id=entry.id, line_no=n, account_id=account.id, debit=debit, credit=credit))
    return entry
