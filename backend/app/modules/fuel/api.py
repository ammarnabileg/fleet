import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.fuel import schemas, service
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.org import service as org

router = APIRouter(prefix="/api/v1", tags=["fuel"])


# ------------------------------------------------------------------ the driver's app (FR-FUL-01)


@router.get("/driver/fuel", response_model=schemas.DriverFuelOut, dependencies=[Depends(org.screen("fuel"))])
def driver_form(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.driver_form(db, device.employee_id)


@router.post(
    "/driver/fuel", response_model=schemas.FillOut, status_code=201, dependencies=[Depends(org.screen("fuel"))]
)
def driver_record(
    body: schemas.DriverFillIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.driver_record(db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump())


# ------------------------------------------------------------------ the office


@router.get("/fuel/fills", response_model=list[schemas.FillOut])
def list_fills(
    status: str | None = None,
    flagged: bool | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("fuel.view")),
    db: Session = Depends(get_session),
):
    return service.list_fills(
        db,
        status=status,
        flagged=flagged,
        vehicle_public_id=vehicle_id,
        driver_public_id=driver_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/fuel/fills", response_model=schemas.FillOut, status_code=201)
def office_record(
    body: schemas.OfficeFillIn,
    principal: Principal = Depends(require_permission("fuel.manage")),
    db: Session = Depends(get_session),
):
    return service.office_record(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.get("/fuel/fills/{public_id}", response_model=schemas.FillOut)
def get(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("fuel.view")),
    db: Session = Depends(get_session),
):
    return service.get(db, public_id, **principal.scope)


@router.get("/fuel/fills/{public_id}/files/{sha256}")
def fill_file(
    public_id: uuid.UUID,
    sha256: str,
    principal: Principal = Depends(require_permission("fuel.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.fill_file(db, public_id, sha256, **principal.scope))


@router.post("/fuel/fills/{public_id}/approve", response_model=schemas.FillOut)
def approve(
    public_id: uuid.UUID,
    body: schemas.DecideIn,
    principal: Principal = Depends(require_permission("fuel.approve")),
    db: Session = Depends(get_session),
):
    return service.decide(
        db, public_id, approve=True, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/fuel/fills/{public_id}/reject", response_model=schemas.FillOut)
def reject(
    public_id: uuid.UUID,
    body: schemas.DecideIn,
    principal: Principal = Depends(require_permission("fuel.approve")),
    db: Session = Depends(get_session),
):
    return service.decide(
        db, public_id, approve=False, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/fuel/consumption", response_model=list[schemas.ConsumptionRow])
def consumption(
    date_from: date,
    date_to: date,
    company_id: int | None = None,
    principal: Principal = Depends(require_permission("fuel.view")),
    db: Session = Depends(get_session),
):
    return service.consumption(db, date_from=date_from, date_to=date_to, company_id=company_id, **principal.scope)


# ------------------------------------------------------------------ references (FR-FUL-02, 04, 05)


@router.get("/fuel/prices", response_model=schemas.PricesOut)
def prices(_: Principal = Depends(require_permission("fuel.view")), db: Session = Depends(get_session)):
    return service.list_prices(db)


@router.post("/fuel/prices", response_model=schemas.PricesOut, status_code=201)
def add_price(
    body: schemas.PriceIn,
    principal: Principal = Depends(require_permission("fuel.manage")),
    db: Session = Depends(get_session),
):
    return service.add_price(db, body.model_dump(), actor_user_id=principal.user_id)


@router.get("/fuel/models", response_model=list[schemas.ModelOut])
def models(_: Principal = Depends(require_permission("fuel.view")), db: Session = Depends(get_session)):
    return service.list_models(db)


@router.post("/fuel/models", response_model=schemas.ModelOut, status_code=201)
def add_model(
    body: schemas.ModelIn,
    principal: Principal = Depends(require_permission("fuel.manage")),
    db: Session = Depends(get_session),
):
    return service.save_model(db, body.model_dump(), model_id=None, version=None, actor_user_id=principal.user_id)


@router.put("/fuel/models/{model_id}", response_model=schemas.ModelOut)
def save_model(
    model_id: int,
    body: schemas.ModelIn,
    principal: Principal = Depends(require_permission("fuel.manage")),
    db: Session = Depends(get_session),
):
    return service.save_model(
        db, body.model_dump(), model_id=model_id, version=body.version, actor_user_id=principal.user_id
    )
