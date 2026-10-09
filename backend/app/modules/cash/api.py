import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import sheets
from app.core.clock import KUWAIT, today
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.cash import fuel, schemas, service
from app.modules.files import service as files
from app.modules.i18n import service as i18n
from app.modules.identity.service import (
    DevicePrincipal,
    Principal,
    get_principal,
    require_device,
    require_permission,
)
from app.modules.org import service as org
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["cash"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _driver(db: Session, raw: str, principal: Principal) -> people.EmployeeRef:
    try:
        public_id = uuid.UUID(raw)
    except ValueError:
        raise AppError(404, "employee_not_found") from None
    driver = people.ref_by_public_id(db, public_id, **principal.scope)
    if not driver.is_driver:
        raise AppError(422, "not_a_driver")
    return driver


# ---- driver app


NEAR_LIMIT = Decimal("0.8")  # the driver is warned from 80% of the alert limit


@router.get("/driver/cash", response_model=schemas.DriverCashOut, dependencies=[Depends(org.screen("cash"))])
def my_cash(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    b = service.driver_balance(db, device.employee_id)
    limit = org.get_section(db, "cash").driver_balance_alert
    return {
        "posted": b.posted,
        "pending": b.pending,
        "total": b.total,
        "alert_limit": limit,
        "near_limit": NEAR_LIMIT * limit <= b.total <= limit,  # warned before the office is (FR-APP-03)
        "receipts": service.receipts_for_driver(db, device.employee_id),
        "lines": service.statement(db, people.ref(db, device.employee_id), limit=30)["lines"],
    }


@router.post(
    "/driver/cash/receipts/{public_id}/confirm",
    response_model=schemas.ReceiptOut,
    dependencies=[Depends(org.screen("cash"))],
)
def confirm_receipt(
    public_id: uuid.UUID, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    """The driver acknowledges the receipt the cashier gave him."""
    return service.confirm_receipt(db, device.employee_id, public_id)


# ---- office


@router.get("/cash/balances", response_model=list[schemas.BalanceOut])
def balances(principal: Principal = Depends(require_permission("cash.view")), db: Session = Depends(get_session)):
    return service.driver_balances(
        db, [d for d in people.app_drivers(db, **principal.scope)] + people.departed_drivers(db, **principal.scope)
    )


@router.get("/cash/receipts/unconfirmed", response_model=list[schemas.UnconfirmedReceiptOut])
def unconfirmed_receipts(
    principal: Principal = Depends(require_permission("cash.view")), db: Session = Depends(get_session)
):
    """Receipts the drivers have not confirmed a day after they were given (FR-CSH-05)."""
    drivers = people.app_drivers(db, **principal.scope) + people.departed_drivers(db, **principal.scope)
    return service.unconfirmed_receipts(db, drivers)


@router.get("/cash/drivers/{driver_id}/statement", response_model=schemas.StatementOut)
def statement(
    driver_id: str, principal: Principal = Depends(require_permission("cash.view")), db: Session = Depends(get_session)
):
    return service.statement(db, _driver(db, driver_id, principal))


@router.post("/cash/receipts", response_model=schemas.ReceiptOut, status_code=201)
def record_receipt(
    body: schemas.ReceiptIn,
    principal: Principal = Depends(require_permission("cash.collect")),
    db: Session = Depends(get_session),
):
    return service.record_receipt(
        db, _driver(db, body.driver_id, principal), amount=body.amount, actor_user_id=principal.user_id
    )


@router.post("/cash/adjustments", response_model=schemas.JournalOut, status_code=201)
def adjust(
    body: schemas.AdjustmentIn,
    principal: Principal = Depends(require_permission("cash.adjust")),
    db: Session = Depends(get_session),
):
    return service.adjust(
        db,
        _driver(db, body.driver_id, principal),
        amount=body.amount,
        reason=body.reason,
        actor_user_id=principal.user_id,
    )


@router.post("/cash/journals/{public_id}/reverse", response_model=schemas.JournalOut, status_code=201)
def reverse(
    public_id: uuid.UUID,
    body: schemas.ReverseIn,
    principal: Principal = Depends(require_permission("cash.reverse")),
    db: Session = Depends(get_session),
):
    return service.reverse(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/cash/settlements", response_model=schemas.SettlementOut, status_code=201)
def settle(
    body: schemas.SettlementIn,
    principal: Principal = Depends(require_permission("cash.writeoff")),
    db: Session = Depends(get_session),
):
    """End of service: brings the driver's cash account to zero and closes it."""
    return service.settle(
        db,
        _driver(db, body.driver_id, principal),
        payroll_amount=body.payroll_amount,
        writeoff_amount=body.writeoff_amount,
        reason=body.reason,
        actor_user_id=principal.user_id,
    )


@router.get("/cash/treasury", response_model=list[schemas.TreasuryOut])
def treasury(principal: Principal = Depends(require_permission("treasury.view")), db: Session = Depends(get_session)):
    return service.treasury(db)


@router.post("/cash/bank-deposits", response_model=schemas.JournalOut, status_code=201)
def bank_deposit(
    body: schemas.BankDepositIn,
    principal: Principal = Depends(require_permission("treasury.manage")),
    db: Session = Depends(get_session),
):
    if not principal.sees_all_companies:  # the treasury is shared by every company of the branch
        raise AppError(403, "company_out_of_scope")
    return service.bank_deposit(
        db,
        branch_id=body.branch_id,
        amount=body.amount,
        reference=body.reference,
        receipt_sha256=body.receipt_sha256,
        actor_user_id=principal.user_id,
    )


@router.post("/cash/bank-withdrawals", response_model=schemas.JournalOut, status_code=201)
def bank_withdrawal(
    body: schemas.BankWithdrawalIn,
    principal: Principal = Depends(require_permission("treasury.manage")),
    db: Session = Depends(get_session),
):
    """Cash taken from the bank to a branch treasury, with the photo of the withdrawal slip."""
    if not principal.sees_all_companies:  # the treasury and the bank are shared by every company of the branch
        raise AppError(403, "company_out_of_scope")
    return service.bank_withdrawal(
        db,
        branch_id=body.branch_id,
        amount=body.amount,
        reference=body.reference,
        attachment_sha256=body.attachment_sha256,
        actor_user_id=principal.user_id,
    )


def _movements(db: Session, principal: Principal, branch_public_id, account, date_from, date_to, limit) -> dict:
    first = today().replace(day=1)
    return service.movements(
        db,
        branch_public_id,
        kind=account,
        date_from=date_from or first,
        date_to=date_to or today(),
        limit=limit,
        can_reverse=principal.has("cash.reverse"),
        **principal.scope,
    )


@router.get("/cash/treasury/{branch_public_id}/movements", response_model=schemas.MovementsOut)
def movements(
    branch_public_id: uuid.UUID,
    account: Literal["treasury", "bank"] = "treasury",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=service.MOVEMENTS_MAX)] = 500,
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """A branch's treasury or bank as it moved in a period (this month by default), with its running balance."""
    return _movements(db, principal, branch_public_id, account, date_from, date_to, limit)


MOVEMENT_COLUMNS = ("date", "time", "kind", "description", "amount", "balance")


@router.get("/cash/treasury/{branch_public_id}/movements/export")
def export_movements(
    branch_public_id: uuid.UUID,
    account: Literal["treasury", "bank"] = "treasury",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    accept_language: str | None = Header(None),
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """The same movements in Excel, with the opening and closing balances."""
    out = _movements(db, principal, branch_public_id, account, date_from, date_to, service.MOVEMENTS_MAX)
    lang = i18n.negotiate(db, principal.locale, accept_language)

    def text(key: str, fallback: str) -> str:
        value = i18n.t(db, lang, key)
        return fallback if value == key else value

    def describe(ln: dict) -> str:
        parts = [i18n.pick(ln["driver"]["name"], lang, lang) if ln["driver"] else ""]
        if ln["receipt_no"]:
            parts.append(f"#{ln['receipt_no']}")
        parts.append(ln["description"] or "")
        return " · ".join(p for p in parts if p)

    def kind(ln: dict) -> str:
        label = text(f"journal_kind.{ln['kind']}", ln["kind"])
        undone = ln["reverses_kind"]
        return f"{label}: {text('journal_kind.' + undone, undone)}" if undone else label

    body = [["", "", text("treasury_column.opening", "opening"), "", "", f"{out['opening']:.3f}"]]
    body += [
        [
            ln["business_date"].isoformat(),
            ln["created_at"].astimezone(KUWAIT).strftime("%H:%M"),
            kind(ln),
            describe(ln),
            f"{ln['amount']:.3f}",
            f"{ln['balance']:.3f}",
        ]
        for ln in out["lines"]
    ]
    body.append(["", "", text("treasury_column.closing", "closing"), "", "", f"{out['closing']:.3f}"])
    header = [text(f"treasury_column.{c}", c) for c in MOVEMENT_COLUMNS]
    content = sheets.to_xlsx(text(f"treasury_column.{account}", account), header, body, rtl=lang == "ar")
    name = f"{account}-{out['date_from']}-{out['date_to']}.xlsx"
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _all_companies(principal: Principal) -> None:
    if not principal.sees_all_companies:  # a branch's treasury is shared by every company of the branch
        raise AppError(403, "company_out_of_scope")


@router.get("/cash/treasury/{branch_public_id}/closing", response_model=schemas.ClosingDayOut)
def closing_day(
    branch_public_id: uuid.UUID,
    day: date | None = None,
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """For the count-and-close dialog: the day to close next, and the treasury's balance at the end of a day."""
    _all_companies(principal)
    return service.closing_day(db, branch_public_id, day=day)


@router.post("/cash/treasury/{branch_public_id}/close", response_model=schemas.ClosingOut, status_code=201)
def close_day(
    branch_public_id: uuid.UUID,
    body: schemas.CloseDayIn,
    principal: Principal = Depends(require_permission("treasury.manage")),
    db: Session = Depends(get_session),
):
    """The day's cash counted and the day closed: a difference is posted with its explanation."""
    _all_companies(principal)
    return service.close_day(
        db,
        branch_public_id,
        day=body.day,
        counted=body.counted,
        denominations=body.denominations,
        note=body.note,
        actor_user_id=principal.user_id,
    )


@router.get("/cash/treasury/{branch_public_id}/closings", response_model=schemas.ClosingsOut)
def closings(
    branch_public_id: uuid.UUID,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """A branch treasury's closings, the last 62 days by default."""
    _all_companies(principal)
    last = date_to or today()
    return service.closings(db, branch_public_id, date_from=date_from or last - timedelta(days=61), date_to=last)


@router.post("/cash/treasury/closings/{public_id}/reopen", response_model=schemas.ClosingOut)
def reopen_closing(
    public_id: uuid.UUID,
    body: schemas.ReopenIn,
    principal: Principal = Depends(require_permission("treasury.manage")),
    db: Session = Depends(get_session),
):
    """The branch's last closing reopened, with the reason: its difference is reversed."""
    _all_companies(principal)
    return service.reopen_closing(db, public_id, reason=body.reason, actor_user_id=principal.user_id)


# ---- petty cash custody (not a company's: an all-companies user)


def _holder(db: Session, raw: uuid.UUID) -> people.EmployeeRef:
    return people.ref_by_public_id(db, raw, all_companies=True, company_ids=[])


@router.get("/cash/petty", response_model=list[schemas.PettyHolderOut])
def petty_holders(
    principal: Principal = Depends(require_permission("treasury.view")), db: Session = Depends(get_session)
):
    """Who holds a petty cash custody, how much, and when it last moved."""
    _all_companies(principal)
    return service.petty_holders(db)


@router.post("/cash/petty/{employee_id}/fund", response_model=schemas.JournalOut, status_code=201)
def petty_fund(
    employee_id: uuid.UUID,
    body: schemas.PettyMoveIn,
    principal: Principal = Depends(require_permission("treasury.manage")),
    db: Session = Depends(get_session),
):
    """Cash from a branch treasury to an employee's custody."""
    _all_companies(principal)
    return service.petty_fund(
        db,
        _holder(db, employee_id),
        branch_id=body.branch_id,
        amount=body.amount,
        note=body.note,
        actor_user_id=principal.user_id,
    )


@router.post("/cash/petty/{employee_id}/return", response_model=schemas.JournalOut, status_code=201)
def petty_return(
    employee_id: uuid.UUID,
    body: schemas.PettyMoveIn,
    principal: Principal = Depends(require_permission("treasury.manage")),
    db: Session = Depends(get_session),
):
    """What is left of a custody, back to a branch treasury."""
    _all_companies(principal)
    return service.petty_return(
        db,
        _holder(db, employee_id),
        branch_id=body.branch_id,
        amount=body.amount,
        note=body.note,
        actor_user_id=principal.user_id,
    )


@router.get("/cash/petty/{employee_id}/movements", response_model=schemas.PettyMovementsOut)
def petty_movements(
    employee_id: uuid.UUID,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=service.MOVEMENTS_MAX)] = 500,
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """A custody as it moved in a period (this month by default), with its running balance."""
    _all_companies(principal)
    return service.petty_movements(
        db,
        _holder(db, employee_id),
        date_from=date_from or today().replace(day=1),
        date_to=date_to or today(),
        limit=limit,
        can_reverse=principal.has("cash.reverse"),
        **principal.scope,
    )


@router.get("/cash/journals/{public_id}/attachment")
def journal_attachment(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """The bank receipt's photo of a deposit."""
    return files.response(db, service.journal_attachment(db, public_id, **principal.scope))


# ---- fuel the driver paid from his cash


@router.get("/driver/fuel", response_model=schemas.DriverFuelOut, dependencies=[Depends(org.screen("fuel"))])
def my_fuel(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """Whether he may claim fuel now (and why not), the most one claim may be, and his last claims."""
    return fuel.driver_view(db, device.employee_id)


@router.post(
    "/driver/fuel",
    response_model=schemas.DriverFuelClaimOut,
    status_code=201,
    dependencies=[Depends(org.screen("fuel"))],
)
def claim_fuel(
    body: schemas.FuelClaimIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return fuel.driver_claim(db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump())


def _fuel_reader(principal: Principal = Depends(get_principal)) -> Principal:
    """The cash ledger's readers and the fuel reviewers see the claims."""
    if not (principal.has("cash.view") or principal.has("cash.fuel_review")):
        raise AppError(403, "permission_denied", permission="cash.fuel_review")
    return principal


@router.get("/cash/fuel-claims", response_model=list[schemas.FuelClaimOut])
def fuel_claims(
    status: Literal["pending", "approved", "rejected"] | None = None,
    driver_id: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    principal: Principal = Depends(_fuel_reader),
    db: Session = Depends(get_session),
):
    driver = _driver(db, driver_id, principal).id if driver_id else None
    return fuel.list_claims(
        db,
        status=status,
        driver_id=driver,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        **principal.scope,
    )


@router.get("/cash/fuel-claims/pending-count", response_model=schemas.CountOut)
def fuel_pending(principal: Principal = Depends(_fuel_reader), db: Session = Depends(get_session)):
    return {"count": fuel.pending_count(db, **principal.scope)}


@router.get("/cash/fuel-claims/{public_id}/receipt")
def fuel_receipt(
    public_id: uuid.UUID, principal: Principal = Depends(_fuel_reader), db: Session = Depends(get_session)
):
    return files.response(db, fuel.receipt(db, public_id, **principal.scope))


@router.post("/cash/fuel-claims/{public_id}/approve", response_model=schemas.FuelClaimOut)
def approve_fuel(
    public_id: uuid.UUID,
    body: schemas.FuelApproveIn,
    principal: Principal = Depends(require_permission("cash.fuel_review")),
    db: Session = Depends(get_session),
):
    return fuel.approve(
        db, public_id, amount=body.amount, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/cash/fuel-claims/{public_id}/reject", response_model=schemas.FuelClaimOut)
def reject_fuel(
    public_id: uuid.UUID,
    body: schemas.FuelRejectIn,
    principal: Principal = Depends(require_permission("cash.fuel_review")),
    db: Session = Depends(get_session),
):
    return fuel.reject(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)
