import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.files import service as files
from app.modules.identity.service import (
    DevicePrincipal,
    Principal,
    get_principal,
    require_device,
    require_permission,
)
from app.modules.org import service as org
from app.modules.payroll import (
    columns,
    export,
    objections,
    platforms,
    runs,
    schemas,
    schemes,
    service,
    statements,
    uncollected,
)
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["payroll"])


@router.get("/deductions", response_model=list[schemas.DeductionOut])
def list_deductions(
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
    employee_id: uuid.UUID | None = None,
    month: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("deductions.view")),
    db: Session = Depends(get_session),
):
    return service.list_deductions(
        db,
        status=status,
        employee_public_id=employee_id,
        month=month,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/deductions/{public_id}/cancel", response_model=schemas.DeductionOut)
def cancel(
    public_id: uuid.UUID,
    body: schemas.CancelIn,
    principal: Principal = Depends(require_permission("deductions.manage")),
    db: Session = Depends(get_session),
):
    return service.cancel(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.get("/driver/deductions", response_model=list[schemas.DeductionOut])
def my_deductions(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """What the driver sees in the app: every live deduction with its monthly installments."""
    return service.for_employee(db, device.employee_id)


@router.post("/deductions", response_model=schemas.DeductionOut, status_code=201)
def create_deduction(
    body: schemas.DeductionIn,
    principal: Principal = Depends(require_permission("deductions.manage")),
    db: Session = Depends(get_session),
):
    """An advance, a phone SIM card or another deduction, in monthly installments."""
    return service.create_manual(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


# ------------------------------------------------------------------ platforms


@router.get("/payroll/platforms", response_model=list[schemas.PlatformOut])
def list_platforms(_: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    """Visible to everyone signed in: the employee form picks a driver's platform from here."""
    return platforms.list_platforms(db)


@router.post("/payroll/platforms", response_model=schemas.PlatformOut, status_code=201)
def create_platform(
    body: schemas.PlatformIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return platforms.create(db, body.model_dump(), actor_user_id=principal.user_id)


@router.patch("/payroll/platforms/{platform_id}", response_model=schemas.PlatformOut)
def update_platform(
    platform_id: int,
    body: schemas.PlatformUpdateIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return platforms.update(db, platform_id, version=version, changes=changes, actor_user_id=principal.user_id)


@router.post("/payroll/platforms/template", response_model=list[schemas.TemplateSheet])
def read_template(file: UploadFile, _: Principal = Depends(require_permission("settings.update"))):
    """The client's salary template (Excel): each sheet's columns with what they hold, to set a platform up from."""
    return columns.read_template(files.read_upload(file))


# ------------------------------------------------------------------ monthly platform statements


@router.get("/payroll/statements", response_model=list[schemas.StatementOut])
def list_statements(
    month: date | None = None,
    status: Literal["submitted", "approved", "rejected"] | None = None,
    platform_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return statements.list_statements(
        db, month=month, status=status, platform_id=platform_id, limit=limit, offset=offset, **principal.scope
    )


@router.get("/payroll/statements/counts")
def statement_counts(
    principal: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return statements.counts(db, **principal.scope)


@router.post("/payroll/statements", response_model=schemas.StatementOut, status_code=201)
def enter_statement(
    body: schemas.OfficeStatementIn,
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    """A month entered by the office (from the platform's report): approved at once."""
    return statements.office_create(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.get("/payroll/statements/{public_id}", response_model=schemas.StatementOut)
def statement_detail(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return statements.detail(db, public_id, **principal.scope)


@router.get("/payroll/statements/{public_id}/files/{sha256}")
def statement_file(
    public_id: uuid.UUID,
    sha256: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, statements.screenshot(db, public_id, sha256, **principal.scope))


@router.post("/payroll/statements/{public_id}/approve", response_model=schemas.StatementOut)
def approve_statement(
    public_id: uuid.UUID,
    body: schemas.ApproveStatementIn,
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    return statements.approve(db, public_id, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.post("/payroll/statements/{public_id}/reject", response_model=schemas.StatementOut)
def reject_statement(
    public_id: uuid.UUID,
    body: schemas.CancelIn,
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    return statements.reject(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.get(
    "/driver/statements", response_model=schemas.DriverPlatformOut, dependencies=[Depends(org.screen("statement"))]
)
def my_statements(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """The driver's platform, what it asks for, the months he can send now and what he sent."""
    return statements.driver_view(db, device.employee_id)


@router.post(
    "/driver/statements",
    response_model=schemas.DriverPlatformOut,
    status_code=201,
    dependencies=[Depends(org.screen("statement"))],
)
def send_statement(
    body: schemas.DriverStatementIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """The month's screenshots from the platform's app and the figures read from them."""
    return statements.driver_submit(db, device.employee_id, device.device_id, body.model_dump())


# ------------------------------------------------------------------ payroll runs


@router.get("/payroll/gate")
def payroll_gate(_: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)):
    """Whether runs may be approved yet (the reconciliation gate in the payroll settings)."""
    return {"live_approval_enabled": runs.live_approval(db)}


@router.get("/payroll/runs", response_model=list[schemas.RunOut])
def list_runs(
    company_id: int | None = None,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return runs.list_runs(db, company_id=company_id, **principal.scope)


@router.post("/payroll/runs", response_model=schemas.RunDetail, status_code=201)
def prepare_run(
    body: schemas.RunIn,
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    return runs.prepare(
        db, company_id=body.company_id, month=body.month, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/payroll/runs/{public_id}", response_model=schemas.RunDetail)
def run_detail(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return runs.detail(db, public_id, **principal.scope)


@router.post("/payroll/runs/{public_id}/recompute", response_model=schemas.RunDetail)
def recompute_run(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    return runs.recompute(db, public_id, actor_user_id=principal.user_id, **principal.scope)


@router.post("/payroll/runs/{public_id}/approve", response_model=schemas.RunDetail)
def approve_run(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.approve")),
    db: Session = Depends(get_session),
):
    return runs.approve(db, public_id, actor_user_id=principal.user_id, **principal.scope)


@router.post("/payroll/runs/{public_id}/reopen", response_model=schemas.RunDetail)
def reopen_run(
    public_id: uuid.UUID,
    body: schemas.ReopenIn,
    principal: Principal = Depends(require_permission("payroll.unlock")),
    db: Session = Depends(get_session),
):
    return runs.reopen(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/payroll/runs/{public_id}/paid", response_model=schemas.RunDetail)
def run_paid(
    public_id: uuid.UUID,
    body: schemas.PaidIn,
    principal: Principal = Depends(require_permission("payroll.approve")),
    db: Session = Depends(get_session),
):
    return runs.mark_paid(
        db, public_id, payment_ref=body.payment_ref, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/payroll/runs/{public_id}/export")
def export_run(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.export")),
    db: Session = Depends(get_session),
):
    """The client's salary sheets (Excel): one sheet per platform in its own columns. A draft is marked as such."""
    run, lines = runs.run_for_export(db, public_id, **principal.scope)
    name = f"payroll-{run.month:%Y-%m}-{run.company_id}{'' if run.status != 'draft' else '-draft'}.xlsx"
    return Response(
        export.workbook(db, run, lines),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# ------------------------------------------------------------------ the uncollected deductions balance (decision D)


@router.get("/payroll/uncollected", response_model=list[schemas.UncollectedOut])
def list_uncollected(
    month: date | None = None,
    status: Literal["review", "carried", "dropped"] | None = None,
    employee_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    """What approved months' pay could not cover of their penalties, per month and per driver, for review."""
    return uncollected.list_lines(
        db,
        month=month,
        status=status,
        employee_public_id=employee_id,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.get("/payroll/uncollected/counts")
def uncollected_counts(
    principal: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return uncollected.counts(db, **principal.scope)


@router.post("/payroll/uncollected/{public_id}/carry", response_model=schemas.UncollectedOut)
def carry_uncollected(
    public_id: uuid.UUID,
    body: schemas.UncollectedDecisionIn,
    principal: Principal = Depends(require_permission("payroll.approve")),
    db: Session = Depends(get_session),
):
    """«تُرحّل للشهر التالي»: a manual deduction of the amount from the next month, with the approver's note."""
    return uncollected.carry(
        db, public_id, note=body.note, version=body.version, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/payroll/uncollected/{public_id}/drop", response_model=schemas.UncollectedOut)
def drop_uncollected(
    public_id: uuid.UUID,
    body: schemas.UncollectedDecisionIn,
    principal: Principal = Depends(require_permission("payroll.approve")),
    db: Session = Depends(get_session),
):
    """«إسقاط»: nothing more is taken, with the note why."""
    return uncollected.drop(
        db, public_id, note=body.note, version=body.version, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/driver/payslips", response_model=list[schemas.PayslipOut], dependencies=[Depends(org.screen("payslips"))])
def my_payslips(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """The driver's approved payslips, each in his platform's sheet order (FR-PAY-06)."""
    return runs.payslips(db, device.employee_id)


# ------------------------------------------------------------------ pay schemes (docs/payroll-schemes.md)


@router.get("/payroll/schemes", response_model=list[schemas.SchemeOut])
def list_schemes(
    platform_id: int | None = None,
    _: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return schemes.list_schemes(db, platform_id=platform_id)


@router.post("/payroll/schemes", response_model=schemas.SchemeOut, status_code=201)
def create_scheme(
    body: schemas.SchemeIn,
    principal: Principal = Depends(require_permission("payroll.schemes")),
    db: Session = Depends(get_session),
):
    return schemes.create(db, body.model_dump(), actor_user_id=principal.user_id)


@router.patch("/payroll/schemes/{public_id}", response_model=schemas.SchemeOut)
def update_scheme(
    public_id: uuid.UUID,
    body: schemas.SchemeUpdateIn,
    principal: Principal = Depends(require_permission("payroll.schemes")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    return schemes.update(db, public_id, version=body.version, changes=changes, actor_user_id=principal.user_id)


@router.post("/payroll/schemes/{public_id}/assign", response_model=schemas.AssignSchemeOut)
def assign_scheme(
    public_id: uuid.UUID,
    body: schemas.AssignSchemeIn,
    principal: Principal = Depends(require_permission("payroll.schemes")),
    db: Session = Depends(get_session),
):
    """Drivers on this scheme from a month on: a first assignment, or everyone moved to a new price."""
    return schemes.assign_many(
        db, public_id, body.employee_ids, body.month, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/employees/{public_id}/schemes", response_model=list[schemas.SchemeHistoryOut])
def scheme_history(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return schemes.history(db, people.ref_by_public_id(db, public_id, **principal.scope).id)


@router.get("/payroll/scheme-requests", response_model=list[schemas.SchemeRequestOut])
def scheme_requests(
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return schemes.list_requests(db, status=status, limit=limit, offset=offset, **principal.scope)


@router.get("/payroll/scheme-requests/counts")
def scheme_request_counts(
    principal: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return schemes.request_counts(db, **principal.scope)


@router.post("/payroll/scheme-requests/{public_id}/approve", response_model=schemas.SchemeRequestOut)
def approve_scheme_request(
    public_id: uuid.UUID,
    body: schemas.ApproveSchemeRequestIn,
    principal: Principal = Depends(require_permission("payroll.schemes")),
    db: Session = Depends(get_session),
):
    """The driver moves to the scheme he asked for, from the first month without an approved payroll."""
    return schemes.approve(
        db,
        public_id,
        version=body.version,
        month=body.month,
        note=body.note,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/payroll/scheme-requests/{public_id}/reject", response_model=schemas.SchemeRequestOut)
def reject_scheme_request(
    public_id: uuid.UUID,
    body: schemas.RejectSchemeRequestIn,
    principal: Principal = Depends(require_permission("payroll.schemes")),
    db: Session = Depends(get_session),
):
    return schemes.reject(
        db, public_id, version=body.version, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/driver/schemes", response_model=schemas.DriverSchemesOut, dependencies=[Depends(org.screen("schemes"))])
def my_schemes(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """His platform's schemes with their terms, his scheme this month and next, and his latest request."""
    return schemes.driver_view(db, device.employee_id)


@router.post(
    "/driver/scheme-requests",
    response_model=schemas.DriverSchemesOut,
    status_code=201,
    dependencies=[Depends(org.screen("schemes"))],
)
def ask_scheme(
    body: schemas.SchemeRequestIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """A request to move to another scheme from next month: the office decides."""
    return schemes.request_change(
        db, device.employee_id, device_id=device.device_id, scheme_public_id=body.scheme_id, note=body.note
    )


@router.delete(
    "/driver/scheme-requests/{public_id}",
    response_model=schemas.DriverSchemesOut,
    dependencies=[Depends(org.screen("schemes"))],
)
def cancel_scheme_request(
    public_id: uuid.UUID, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return schemes.cancel(db, device.employee_id, public_id)


# ------------------------------------------------------------------ objections to a payslip

_ONE = "(open|in_review|accepted|rejected|closed)"
OBJECTION_STATUSES = rf"^{_ONE}(,{_ONE})*$"  # one or more, comma-separated


def _answers_objections(principal: Principal = Depends(get_principal)) -> Principal:
    """Who prepares or approves payroll answers the drivers' objections."""
    if not (principal.has("payroll.prepare") or principal.has("payroll.approve")):
        raise AppError(403, "permission_denied", permission="payroll.prepare | payroll.approve")
    return principal


@router.get(
    "/driver/objections", response_model=list[schemas.ObjectionOut], dependencies=[Depends(org.screen("payslips"))]
)
def my_objections(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """His objections, newest first, with their status and the office's answer."""
    return objections.driver_list(db, device.employee_id)


@router.post(
    "/driver/payslips/{run_id}/objections",
    response_model=schemas.ObjectionOut,
    status_code=201,
    dependencies=[Depends(org.screen("payslips"))],
)
def object_to_payslip(
    run_id: uuid.UUID,
    body: schemas.ObjectionIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """An objection to his payslip of that run: all of it, or one line (item_code), with a photo or PDF if any."""
    return objections.driver_create(
        db, device.employee_id, device_id=device.device_id, run_public_id=run_id, data=body.model_dump()
    )


@router.get("/driver/objections/{public_id}/attachment", dependencies=[Depends(org.screen("payslips"))])
def my_objection_file(
    public_id: uuid.UUID, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return files.response(db, objections.driver_attachment(db, device.employee_id, public_id))


@router.get("/payroll/objections", response_model=list[schemas.OfficeObjectionOut])
def list_objections(
    status: str | None = Query(
        None, pattern=r"^(open|in_review|accepted|rejected|closed)(,(open|in_review|accepted|rejected|closed))*$"
    ),
    month: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return objections.list_objections(db, status=status, month=month, limit=limit, offset=offset, **principal.scope)


@router.get("/payroll/objections/counts")
def objection_counts(
    principal: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return objections.counts(db, **principal.scope)


@router.get("/payroll/objections/{public_id}", response_model=schemas.OfficeObjectionOut)
def objection_detail(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return objections.detail(db, public_id, **principal.scope)


@router.get("/payroll/objections/{public_id}/attachment")
def objection_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, objections.attachment(db, public_id, **principal.scope))


@router.post("/payroll/objections/{public_id}/respond", response_model=schemas.OfficeObjectionOut)
def answer_objection(
    public_id: uuid.UUID,
    body: schemas.ObjectionAnswerIn,
    principal: Principal = Depends(_answers_objections),
    db: Session = Depends(get_session),
):
    """In review, accepted or rejected with the answer the driver reads, or closed; a settlement deduction linked. The
    approved run never changes."""
    return objections.respond(db, public_id, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)
