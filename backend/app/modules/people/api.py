import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.cash import service as cash
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.identity.service import DevicePrincipal, Principal, get_principal, require_device, require_permission
from app.modules.payroll import service as payroll
from app.modules.people import schemas, service

router = APIRouter(prefix="/api/v1", tags=["people"])
SALARY = "employees.view_salary"


@router.get("/employment-statuses", response_model=list[schemas.StatusOut])
def list_statuses(_: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return service.list_statuses(db)


@router.post("/employment-statuses", response_model=schemas.StatusOut, status_code=201)
def create_status(
    body: schemas.StatusIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.create_status(db, body.model_dump(), actor_user_id=principal.user_id)


@router.patch("/employment-statuses/{code}", response_model=schemas.StatusOut)
def update_status(
    code: str,
    body: schemas.StatusUpdateIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.update_status(db, code, body.model_dump(exclude_unset=True), actor_user_id=principal.user_id)


@router.get("/employees", response_model=list[schemas.EmployeeOut])
def list_employees(
    company_id: int | None = None,
    status_code: str | None = None,
    is_driver: bool | None = None,
    platform_id: int | None = None,
    no_phone: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("employees.view")),
    db: Session = Depends(get_session),
):
    return service.list_employees(
        db,
        show_salary=principal.has(SALARY),
        company_id=company_id,
        status_code=status_code,
        is_driver=is_driver,
        platform_id=platform_id,
        no_phone=no_phone,
        q=q,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.get("/employees/{public_id}", response_model=schemas.EmployeeOut)
def get_employee(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("employees.view")),
    db: Session = Depends(get_session),
):
    return service.get_employee(db, public_id, show_salary=principal.has(SALARY), **principal.scope)


@router.post("/employees", response_model=schemas.EmployeeOut, status_code=201)
def create_employee(
    body: schemas.EmployeeIn,
    principal: Principal = Depends(require_permission("employees.create")),
    db: Session = Depends(get_session),
):
    return service.create_employee(
        db,
        body.model_dump(),
        can_set_salary=principal.has(SALARY),
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.patch("/employees/{public_id}", response_model=schemas.EmployeeOut)
def update_employee(
    public_id: uuid.UUID,
    body: schemas.EmployeeUpdateIn,
    principal: Principal = Depends(require_permission("employees.update")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_employee(
        db,
        public_id,
        version=version,
        changes=changes,
        can_set_salary=principal.has(SALARY),
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/employees/{public_id}/status", response_model=schemas.EmployeeOut)
def change_status(
    public_id: uuid.UUID,
    body: schemas.StatusChangeIn,
    principal: Principal = Depends(require_permission("employees.update")),
    db: Session = Depends(get_session),
):
    employee, ended = service.change_status(
        db,
        public_id,
        status_code=body.status_code,
        note=body.note,
        actor_user_id=principal.user_id,
        **principal.scope,
    )
    if ended:
        # the app already refuses the driver (every request checks the status); this also closes the device
        identity.revoke_employee_devices(db, employee.id, reason="employment_ended", actor_user_id=principal.user_id)
        fleet.flag_departed_driver(db, employee)
        cash.flag_departed(db, employee)
    return service.get_employee(db, public_id, show_salary=principal.has(SALARY), **principal.scope)


@router.put("/employees/{public_id}/app-access", response_model=schemas.EmployeeOut)
def set_app_access(
    public_id: uuid.UUID,
    body: schemas.AppAccessIn,
    principal: Principal = Depends(require_permission("devices.manage")),
    db: Session = Depends(get_session),
):
    service.set_app_access(db, public_id, value=body.app_access, actor_user_id=principal.user_id, **principal.scope)
    return service.get_employee(db, public_id, show_salary=principal.has(SALARY), **principal.scope)


@router.get("/employees/{public_id}/status-history", response_model=list[schemas.StatusHistoryOut])
def status_history(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("employees.view")),
    db: Session = Depends(get_session),
):
    return service.status_history(db, public_id, **principal.scope)


@router.put("/employees/{public_id}/external-refs/{system}", status_code=204)
def set_external_ref(
    public_id: uuid.UUID,
    body: schemas.ExternalRefIn,
    system: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,30}$")],
    principal: Principal = Depends(require_permission("integrations.manage")),
    db: Session = Depends(get_session),
):
    service.set_external_ref(
        db,
        public_id,
        system=system,
        external_id=body.external_id,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.get("/driver/profile", response_model=schemas.ProfileOut)
def my_profile(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """The driver's own record (BRD FR-APP-01)."""
    out = service.profile(db, device.employee_id)
    return out | {"platform": payroll.platform_name(db, out.pop("platform_id"))}
