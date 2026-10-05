import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity.service import (
    DevicePrincipal,
    Principal,
    get_principal,
    require_device,
    require_permission,
)
from app.modules.payroll import columns, export, platforms, runs, schemas, service, statements

router = APIRouter(prefix="/api/v1", tags=["payroll"])


@router.get("/deductions", response_model=list[schemas.DeductionOut])
def list_deductions(
    status: Literal["approved", "cancelled"] | None = None,
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


@router.get("/driver/statements", response_model=schemas.DriverPlatformOut)
def my_statements(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """The driver's platform, what it asks for, the months he can send now and what he sent."""
    return statements.driver_view(db, device.employee_id)


@router.post("/driver/statements", response_model=schemas.DriverPlatformOut, status_code=201)
def send_statement(
    body: schemas.DriverStatementIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """The month's screenshots from the platform's app and the figures read from them."""
    return statements.driver_submit(db, device.employee_id, device.device_id, body.model_dump())


# ------------------------------------------------------------------ payroll runs


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


@router.get("/driver/payslips", response_model=list[schemas.PayslipOut])
def my_payslips(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """The driver's approved payslips, each in his platform's sheet order (FR-PAY-06)."""
    return runs.payslips(db, device.employee_id)
