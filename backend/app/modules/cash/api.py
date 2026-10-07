import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.cash import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.org import service as org
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["cash"])


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


@router.get("/cash/journals/{public_id}/attachment")
def journal_attachment(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("treasury.view")),
    db: Session = Depends(get_session),
):
    """The bank receipt's photo of a deposit."""
    return files.response(db, service.journal_attachment(db, public_id))
