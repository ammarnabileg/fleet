import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Signed = Annotated[Decimal, Field(max_digits=12, decimal_places=3)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class ReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: str
    amount: Amount


class ReceiptOut(BaseModel):
    id: str
    receipt_no: int
    branch_id: int
    amount: Decimal
    created_at: datetime
    driver_confirmed_at: datetime | None
    unconfirmed_late: bool = False  # still not confirmed by the driver after 24 hours (FR-CSH-05)


class UnconfirmedReceiptOut(ReceiptOut):
    driver: dict


class AdjustmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: str
    amount: Signed  # + the driver owes more, - less
    reason: Reason


class ReverseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class BankDepositIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: int
    amount: Amount
    reference: Reason  # the bank's deposit reference
    receipt_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]  # the bank receipt's photo


class BankWithdrawalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: int
    amount: Amount
    reference: Reason  # the bank's withdrawal reference
    attachment_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]  # the withdrawal slip's photo


class SettlementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: str
    payroll_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)] = Decimal("0")
    writeoff_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)] = Decimal("0")
    reason: Reason | None = None


class LineOut(BaseModel):
    account: str
    branch_id: int | None
    driver: bool
    amount: Decimal


class JournalOut(BaseModel):
    id: str
    kind: str
    status: str
    business_date: date
    source_type: str
    reason: str | None
    created_at: datetime
    decided_at: datetime | None
    has_attachment: bool = False  # a bank deposit's receipt photo
    lines: list[LineOut]


class StatementLine(BaseModel):
    journal_id: str
    kind: str
    status: str
    amount: Decimal
    business_date: date
    reason: str | None
    source_type: str
    created_at: datetime


class StatementOut(BaseModel):
    posted: Decimal  # approved
    pending: Decimal  # waiting for review ("unapproved")
    total: Decimal
    lines: list[StatementLine]


class SettlementOut(StatementOut):
    closed: bool


class PersonRef(BaseModel):
    id: str
    name: dict[str, str]


class BalanceOut(BaseModel):
    driver: PersonRef
    company_id: int
    posted: Decimal
    pending: Decimal
    total: Decimal
    over_limit: bool


class TreasuryOut(BaseModel):
    branch: dict
    treasury: Decimal
    bank: Decimal
    cod_clearing: Decimal


class MovementLine(BaseModel):
    journal_id: str
    kind: str
    reverses_kind: str | None  # a reversal: the kind of the journal it undoes
    business_date: date
    created_at: datetime
    driver: PersonRef | None  # whose cash it was (a receipt, a settlement)
    receipt_no: int | None
    description: str | None  # a disbursement's document, a bank deposit's or withdrawal's reference, a reason
    amount: Decimal  # + into this account, - out of it
    balance: Decimal  # after this line
    has_attachment: bool
    attachment_type: str | None  # its content type: an image opens in the viewer, a PDF in a new tab
    reversed: bool
    reversible: bool  # this user may reverse it from here
    closed: bool = False  # its day is closed by a count: nothing more moves the treasury on it


class MovementsOut(BaseModel):
    branch: dict
    account: str
    date_from: date
    date_to: date
    closed_through: date | None = None  # the treasury's last day closed by a count
    opening: Decimal
    closing: Decimal
    truncated: bool
    lines: list[MovementLine]


# ---- the treasury's daily count and close

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class CloseDayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    counted: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
    denominations: dict[str, Annotated[int, Field(ge=0, le=1_000_000)]] | None = None  # {"20": 3, "0.250": 4}
    note: Note | None = None  # required when the count differs from the books


class ReopenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class ClosingOut(BaseModel):
    id: str
    branch_id: int
    day: date
    book_balance: Decimal
    counted: Decimal
    denominations: dict[str, int] | None
    difference: Decimal
    note: str | None
    journal_id: str | None
    closed_by: str | None
    closed_at: datetime
    reopened_by: str | None
    reopened_at: datetime | None
    reopen_reason: str | None
    reopenable: bool


class ClosingsOut(BaseModel):
    branch: dict
    last_closed_day: date | None
    lines: list[ClosingOut]


class ClosingDayOut(BaseModel):
    branch: dict
    day: date
    book_balance: Decimal  # the treasury's posted balance at the end of the day
    last_closed_day: date | None
    next_day: date | None  # the day to close next
    open_days: list[date]  # days with movements after the last closing, still open
    denominations: list[str]


class DriverCashOut(BaseModel):
    posted: Decimal
    pending: Decimal
    total: Decimal
    alert_limit: Decimal
    near_limit: bool  # from 80% of the limit up to it; above it the office is alerted
    receipts: list[ReceiptOut]
    lines: list[StatementLine]  # his movements, newest first (FR-APP-03)


# ---- fuel the driver paid from his cash

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class FuelClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_ref: uuid.UUID  # the app's id: a resend is answered fuel_exists
    paid_at: datetime  # when the receipt's photo was taken
    amount: Amount
    odometer_km: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    receipt_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]  # a camera photo of the receipt
    notes: Note | None = None


class DriverFuelClaimOut(BaseModel):
    id: str
    paid_at: datetime
    amount: Decimal
    approved_amount: Decimal | None
    status: str  # pending | approved | rejected
    decision_note: str | None
    odometer_km: int | None
    notes: str | None
    vehicle_plate: str | None
    created_at: datetime


class DriverFuelOut(BaseModel):
    allowed: bool
    reason: Literal["fuel_card", "not_covered", "no_vehicle"] | None  # why the app offers no fuel claim
    max_amount: Decimal
    claims: list[DriverFuelClaimOut]


class FuelClaimOut(BaseModel):
    id: str
    driver: PersonRef
    company_id: int
    branch_id: int
    vehicle_plate: str | None
    paid_at: datetime
    amount: Decimal
    approved_amount: Decimal | None
    odometer_km: int | None
    notes: str | None
    status: str
    decision_note: str | None
    decided_by: str | None
    decided_at: datetime | None
    covered: bool  # the company pays his fuel (his scheme of that month, no fuel card), as it stands now
    fuel_card: bool
    journal_id: str | None  # the posted fuel journal of an approved claim covered by the company
    receipt_url: str
    created_at: datetime


class FuelApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Amount | None = None  # the claimed amount when omitted; a different one needs a note
    note: Note | None = None


class FuelRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class CountOut(BaseModel):
    count: int


# ---- petty cash custody


class PettyMoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: int  # the treasury it comes from, or goes back to
    amount: Amount
    note: Note | None = None


class PettyHolderOut(BaseModel):
    employee: PersonRef
    branch_id: int | None
    balance: Decimal
    last_movement: date | None


class PettyMovementsOut(BaseModel):
    employee: PersonRef | None
    account: str
    date_from: date
    date_to: date
    opening: Decimal
    closing: Decimal
    truncated: bool
    lines: list[MovementLine]
