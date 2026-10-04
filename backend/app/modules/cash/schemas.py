from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

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


class DriverCashOut(BaseModel):
    posted: Decimal
    pending: Decimal
    total: Decimal
    alert_limit: Decimal
    receipts: list[ReceiptOut]
