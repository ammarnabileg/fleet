import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import LocalizedText

Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9A-Za-z][0-9A-Za-z.\-]{0,19}$")]
TypeCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_]{1,30}$")]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
AccountType = Literal["asset", "liability", "equity", "income", "expense"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountIn(_In):
    code: Code
    name: LocalizedText
    type: AccountType


class AccountUpdate(_In):
    version: int
    code: Code | None = None
    name: LocalizedText | None = None
    type: AccountType | None = None
    active: bool | None = None


class RolesIn(_In):
    roles: Annotated[dict[str, int], Field(min_length=1, max_length=50)]


class ExpenseTypeIn(_In):
    code: TypeCode
    name: LocalizedText
    account_id: int
    sort_order: Annotated[int, Field(ge=0, le=10000)] = 100


class ExpenseTypeUpdate(_In):
    name: LocalizedText | None = None
    account_id: int | None = None
    active: bool | None = None
    sort_order: Annotated[int, Field(ge=0, le=10000)] | None = None


class ExpenseIn(_In):
    company_id: int
    branch_id: int | None = None  # whose treasury paid: required when paid from the treasury
    type_id: int
    expense_date: date
    amount: Amount
    quantity: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)] | None = None
    payment_method: Literal["treasury", "bank", "payable", "petty"]
    petty_employee_id: uuid.UUID | None = None  # whose petty cash custody paid: required when paid from one
    supplier: Short | None = None
    reference_no: Short | None = None
    vehicle_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    center_id: uuid.UUID | None = None
    notes: Note | None = None
    files: Annotated[list[Sha], Field(max_length=10)] = []


class ApproveIn(_In):
    note: Short | None = None


class RejectIn(_In):
    note: Reason


class CancelIn(_In):
    reason: Reason


class PayIn(_In):
    paid_from: Literal["treasury", "bank"]
    payment_ref: Short | None = None
    branch_id: int | None = None  # whose treasury paid: required from the treasury (unless the expense names it)


class PeriodIn(_In):
    date_from: date
    date_to: date


class PickIn(_In):
    """Drafts by id, or every draft dated in a period."""

    ids: Annotated[list[uuid.UUID], Field(max_length=1000)] | None = None
    date_from: date | None = None
    date_to: date | None = None


Side = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Memo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ManualLineIn(_In):
    account_id: int
    debit: Side = Decimal("0")
    credit: Side = Decimal("0")
    memo: Memo | None = None
    employee_id: uuid.UUID | None = None  # who the line is with (the account statement's party)


class ManualIn(_In):
    entry_date: date
    description: Description
    company_id: int | None = None
    lines: Annotated[list[ManualLineIn], Field(min_length=2, max_length=200)]


class OpeningLineIn(_In):
    account_id: int
    debit: Side = Decimal("0")
    credit: Side = Decimal("0")
    employee_id: uuid.UUID | None = None


class OpeningIn(_In):
    company_id: int | None = None
    lines: Annotated[list[OpeningLineIn], Field(min_length=1, max_length=500)]


class ReverseIn(_In):
    reason: Reason
    entry_date: date | None = None


class Named(BaseModel):
    id: int
    code: str
    name: dict[str, str]


class AccountOut(Named):
    type: str
    active: bool
    roles: list[str]
    used: bool
    version: int


class RoleOut(BaseModel):
    role: str
    account_id: int | None


class ExpenseTypeOut(Named):
    account_id: int
    active: bool
    sort_order: int


class Ref(BaseModel):
    id: str
    name: dict[str, str] | str


class VehicleRef(BaseModel):
    id: str
    plate_number: str


class ExpenseOut(BaseModel):
    id: str
    number: int
    company_id: int
    branch_id: int | None
    type: Named
    expense_date: date
    amount: Decimal
    quantity: Decimal | None
    payment_method: str
    supplier: str | None
    reference_no: str | None
    vehicle: VehicleRef | None
    employee: Ref | None
    petty_employee: Ref | None = None  # whose petty cash custody paid
    center: Ref | None
    notes: str | None
    status: str
    files: list[str]
    created_by: str | None
    created_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    cancel_reason: str | None
    paid_from: str | None
    paid_at: datetime | None
    paid_by: str | None
    payment_ref: str | None
    unpaid: bool
    version: int


class LineAccount(BaseModel):
    id: int
    code: str
    name: dict[str, str]


class EntryLineOut(BaseModel):
    account: LineAccount
    debit: Decimal
    credit: Decimal
    memo: str | None = None
    employee: Ref | None = None


class EntryOut(BaseModel):
    id: str
    number: int
    entry_date: date
    source_kind: str
    source_ref: str
    company_id: int | None
    description: str
    status: str
    amount: Decimal
    reverses: int | None
    reversed_by: int | None
    reason: str | None
    created_by: str | None
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    lines: list[EntryLineOut] | None


class StaleOut(BaseModel):
    id: str
    number: int
    source_ref: str
    status: str
    entered: Decimal
    document: Decimal


class PostError(BaseModel):
    source_ref: str
    code: str
    params: dict


class PostOut(BaseModel):
    created: int
    by_kind: dict[str, int]
    stale: list[StaleOut]
    errors: list[PostError]


class CountOut(BaseModel):
    count: int


class BalanceAccount(LineAccount):
    type: str


class Party(BaseModel):
    type: str  # employee | center | supplier
    id: str | None
    name: dict[str, str]  # {ar, en}: a supplier written on an expense is the same words in both


class LedgerLine(BaseModel):
    entry_id: uuid.UUID
    number: int
    date: date
    ref: str
    description: str
    reversal: bool
    party: Party | None
    debit: Decimal
    credit: Decimal
    balance: Decimal


class PartyBalance(BaseModel):
    party: Party
    debit: Decimal
    credit: Decimal
    balance: Decimal


class LedgerOut(BaseModel):
    account: BalanceAccount
    opening: Decimal
    debit: Decimal
    credit: Decimal
    closing: Decimal
    lines: list[LedgerLine]
    truncated: bool
    parties: list[PartyBalance]


class BalanceOut(BaseModel):
    account: BalanceAccount
    opening: Decimal
    debit: Decimal
    credit: Decimal
    closing: Decimal


class OpeningOut(BaseModel):
    entry: EntryOut
    difference: Decimal  # debits over credits as given: credited (or debited) to the equity account
    equity_account: LineAccount | None


class ConfigOut(BaseModel):
    entry_approval: str
    fiscal_year_start_month: int
    fiscal_year_start: date
    books_start_date: date | None
    opening_date: date | None


class ImportIssue(BaseModel):
    sheet: str
    row: int | None
    code: str
    params: dict


class ImportTotals(BaseModel):
    debit: Decimal
    credit: Decimal
    difference: Decimal
    lines: int


class ImportOut(BaseModel):
    errors: list[ImportIssue]
    warnings: list[ImportIssue]
    opening: ImportTotals
    entries: int
    lines: int
    applied: bool
    numbers: list[int]  # the entries made


# ---- month close


class PeriodOut(BaseModel):
    month: str  # "2026-09"
    status: str  # open | closed
    closed_by: str | None
    closed_at: datetime | None
    reopened_by: str | None
    reopened_at: datetime | None
    reopen_reason: str | None
    reopenable: bool  # the latest closed month


class Problem(BaseModel):
    code: str  # period_problem.<code>
    params: dict


class PeriodCheckOut(BaseModel):
    month: str
    status: str
    problems: list[Problem]  # empty: ready to close


class PeriodReopenIn(_In):
    reason: Reason
