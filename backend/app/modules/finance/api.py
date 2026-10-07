import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import sheets
from app.core.db import get_session
from app.modules.files import service as files
from app.modules.finance import schemas, service
from app.modules.i18n import service as i18n
from app.modules.identity.service import Principal, require_permission
from app.modules.org import service as org

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_COLUMNS = (
    "number",
    "entry_date",
    "account_code",
    "account_name",
    "debit",
    "credit",
    "description",
    "source_ref",
    "company",
    "status",
)

view = require_permission("finance.view")
create = require_permission("finance.create")
approve = require_permission("finance.approve")


# ---- the chart of accounts, its roles, and the expense types (the accountant's)


@router.get("/accounts", response_model=list[schemas.AccountOut])
def accounts(_: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.list_accounts(db)


@router.post("/accounts", response_model=schemas.AccountOut, status_code=201)
def create_account(
    body: schemas.AccountIn, principal: Principal = Depends(approve), db: Session = Depends(get_session)
):
    i18n.validate_localized(db, body.name)
    return service.create_account(db, body.model_dump(), actor_user_id=principal.user_id)


@router.patch("/accounts/{account_id}", response_model=schemas.AccountOut)
def update_account(
    account_id: int,
    body: schemas.AccountUpdate,
    principal: Principal = Depends(approve),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    if "name" in changes:
        i18n.validate_localized(db, body.name)
    return service.update_account(db, account_id, changes, version=body.version, actor_user_id=principal.user_id)


@router.get("/roles", response_model=list[schemas.RoleOut])
def roles(_: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.roles(db)


@router.put("/roles", response_model=list[schemas.RoleOut])
def set_roles(body: schemas.RolesIn, principal: Principal = Depends(approve), db: Session = Depends(get_session)):
    return service.set_roles(db, body.roles, actor_user_id=principal.user_id)


@router.get("/expense-types", response_model=list[schemas.ExpenseTypeOut])
def expense_types(_: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.list_types(db)


@router.post("/expense-types", response_model=schemas.ExpenseTypeOut, status_code=201)
def create_type(
    body: schemas.ExpenseTypeIn, principal: Principal = Depends(approve), db: Session = Depends(get_session)
):
    i18n.validate_localized(db, body.name)
    return service.create_type(db, body.model_dump(), actor_user_id=principal.user_id)


@router.patch("/expense-types/{type_id}", response_model=schemas.ExpenseTypeOut)
def update_type(
    type_id: int,
    body: schemas.ExpenseTypeUpdate,
    principal: Principal = Depends(approve),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        i18n.validate_localized(db, body.name)
    return service.update_type(db, type_id, changes, actor_user_id=principal.user_id)


# ---- expenses (FR-FIN-01, FR-FIN-02)


@router.get("/expenses", response_model=list[schemas.ExpenseOut])
def expenses(
    status: str | None = None,
    type_id: int | None = None,
    vehicle_id: uuid.UUID | None = None,
    unpaid: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(view),
    db: Session = Depends(get_session),
):
    return service.list_expenses(
        db,
        status=status,
        type_id=type_id,
        vehicle_id=vehicle_id,
        unpaid=unpaid,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/expenses", response_model=schemas.ExpenseOut, status_code=201)
def create_expense(body: schemas.ExpenseIn, principal: Principal = Depends(create), db: Session = Depends(get_session)):
    return service.create_expense(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.get("/expenses/{public_id}", response_model=schemas.ExpenseOut)
def get_expense(public_id: uuid.UUID, principal: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.get_expense(db, public_id, **principal.scope)


@router.get("/expenses/{public_id}/files/{sha256}")
def expense_file(
    public_id: uuid.UUID, sha256: str, principal: Principal = Depends(view), db: Session = Depends(get_session)
):
    return files.response(db, service.expense_file(db, public_id, sha256, **principal.scope))


@router.post("/expenses/{public_id}/approve", response_model=schemas.ExpenseOut)
def approve_expense(
    public_id: uuid.UUID,
    body: schemas.ApproveIn,
    principal: Principal = Depends(approve),
    db: Session = Depends(get_session),
):
    return service.decide_expense(
        db, public_id, approve=True, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/expenses/{public_id}/reject", response_model=schemas.ExpenseOut)
def reject_expense(
    public_id: uuid.UUID,
    body: schemas.RejectIn,
    principal: Principal = Depends(approve),
    db: Session = Depends(get_session),
):
    return service.decide_expense(
        db, public_id, approve=False, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/expenses/{public_id}/cancel", response_model=schemas.ExpenseOut)
def cancel_expense(
    public_id: uuid.UUID,
    body: schemas.CancelIn,
    principal: Principal = Depends(create),
    db: Session = Depends(get_session),
):
    return service.cancel_expense(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/expenses/{public_id}/pay", response_model=schemas.ExpenseOut)
def pay_expense(
    public_id: uuid.UUID,
    body: schemas.PayIn,
    principal: Principal = Depends(create),
    db: Session = Depends(get_session),
):
    return service.pay_expense(
        db,
        public_id,
        paid_from=body.paid_from,
        payment_ref=body.payment_ref,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


# ---- journal entries (FR-FIN-03..05)


@router.post("/entries/post", response_model=schemas.PostOut)
def post_entries(body: schemas.PeriodIn, principal: Principal = Depends(create), db: Session = Depends(get_session)):
    """Draft entries for the period's documents without one, and the entries whose document changed since."""
    return service.post(db, body.date_from, body.date_to, actor_user_id=principal.user_id, **principal.scope)


@router.get("/entries", response_model=list[schemas.EntryOut])
def entries(
    status: str | None = None,
    source_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: int | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(view),
    db: Session = Depends(get_session),
):
    return service.list_entries(
        db,
        status=status,
        source_kind=source_kind,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        q=q,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.get("/entries/export")
def export_entries(
    date_from: date,
    date_to: date,
    status: str = "approved",
    format: Literal["xlsx", "csv"] = "xlsx",
    accept_language: str | None = Header(None),
    principal: Principal = Depends(require_permission("finance.export")),
    db: Session = Depends(get_session),
):
    """One row per line, for the client's accounting system (FR-FIN-04): approved entries unless asked otherwise."""
    rows = service.export_lines(db, status=status, date_from=date_from, date_to=date_to, **principal.scope)
    lang = i18n.negotiate(db, principal.locale, accept_language)
    default = i18n.default_language(db).code
    companies = {c["id"]: c["name"] for c in org.list_companies(db, all_companies=True, company_ids=())}

    def name(n: dict | None) -> str:
        return "" if not n else n.get(lang) or n.get(default) or next(iter(n.values()), "")

    def text(key: str, fallback: str) -> str:
        value = i18n.t(db, lang, key)
        return fallback if value == key else value

    body = [
        [
            r["entry"].number,
            r["entry"].entry_date.isoformat(),
            r["account"].code,
            name(r["account"].name),
            f"{r['line'].debit:.3f}" if r["line"].debit else "",
            f"{r['line'].credit:.3f}" if r["line"].credit else "",
            r["entry"].description,
            r["entry"].source_ref,
            name(companies.get(r["entry"].company_id)),
            r["entry"].status if format == "csv" else text(f"entry_status.{r['entry'].status}", r["entry"].status),
        ]
        for r in rows
    ]
    base = f"entries-{date_from}-{date_to}"
    if format == "csv":
        content, media = sheets.to_csv(list(EXPORT_COLUMNS), body), "text/csv; charset=utf-8"
    else:
        header = [text(f"finance_column.{c}", c) for c in EXPORT_COLUMNS]
        content, media = (
            sheets.to_xlsx(
                text("finance_column.title", "entries"), header, body, rtl=lang == "ar", text_columns=(2, 7)
            ),
            XLSX,
        )
    return Response(
        content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{base}.{format}"'}
    )


@router.get("/entries/{public_id}", response_model=schemas.EntryOut)
def get_entry(public_id: uuid.UUID, principal: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.get_entry(db, public_id, **principal.scope)


@router.post("/entries/approve", response_model=schemas.CountOut)
def approve_entries(body: schemas.PickIn, principal: Principal = Depends(approve), db: Session = Depends(get_session)):
    n = service.approve_entries(
        db,
        ids=body.ids,
        date_from=body.date_from,
        date_to=body.date_to,
        actor_user_id=principal.user_id,
        **principal.scope,
    )
    return {"count": n}


@router.post("/entries/discard", response_model=schemas.CountOut)
def discard_drafts(body: schemas.PickIn, principal: Principal = Depends(approve), db: Session = Depends(get_session)):
    n = service.discard_drafts(
        db,
        ids=body.ids,
        date_from=body.date_from,
        date_to=body.date_to,
        actor_user_id=principal.user_id,
        **principal.scope,
    )
    return {"count": n}


@router.post("/entries/{public_id}/reverse", response_model=schemas.EntryOut)
def reverse_entry(
    public_id: uuid.UUID,
    body: schemas.ReverseIn,
    principal: Principal = Depends(approve),
    db: Session = Depends(get_session),
):
    return service.reverse_entry(
        db, public_id, reason=body.reason, day=body.entry_date, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/trial-balance", response_model=list[schemas.BalanceOut])
def trial_balance(
    date_from: date, date_to: date, principal: Principal = Depends(view), db: Session = Depends(get_session)
):
    return service.trial_balance(db, date_from, date_to, **principal.scope)
