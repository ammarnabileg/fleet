import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.onboarding import schemas, service

router = APIRouter(prefix="/api/v1", tags=["onboarding"])
REVIEW = "employees.onboarding"


# ---- driver app


@router.get("/driver/onboarding", response_model=schemas.DriverView)
def driver_view(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.for_driver(db, device.employee_id)


@router.put("/driver/onboarding", response_model=schemas.DriverView)
def save_draft(
    body: schemas.Draft, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    """Saved as the driver goes; gaps are fine until he submits."""
    return service.save_draft(db, device.employee_id, body.model_dump(mode="json"))


@router.post("/driver/onboarding/submit", response_model=schemas.DriverView)
def submit(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.submit(db, device.employee_id)


# ---- review


@router.get("/onboarding", response_model=list[schemas.SubmissionOut])
def list_submissions(
    status: str | None = "submitted",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission(REVIEW)),
    db: Session = Depends(get_session),
):
    return service.list_submissions(db, status=status, limit=limit, offset=offset, **principal.scope)


@router.get("/onboarding/{public_id}", response_model=schemas.SubmissionDetail)
def detail(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission(REVIEW)),
    db: Session = Depends(get_session),
):
    return service.detail(db, public_id, **principal.scope)


@router.get("/onboarding/{public_id}/files/{sha256}")
def submission_file(
    public_id: uuid.UUID,
    sha256: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    principal: Principal = Depends(require_permission(REVIEW)),
    db: Session = Depends(get_session),
):
    info = service.file(db, public_id, sha256, **principal.scope)
    return files.response(db, info)


@router.post("/onboarding/{public_id}/approve", response_model=schemas.SubmissionDetail)
def approve(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission(REVIEW)),
    db: Session = Depends(get_session),
):
    """Employee data, documents and custody, all at once or nothing."""
    return service.approve(db, public_id, actor_user_id=principal.user_id, **principal.scope)


@router.post("/onboarding/{public_id}/reject", response_model=schemas.SubmissionDetail)
def reject(
    public_id: uuid.UUID,
    body: schemas.RejectIn,
    principal: Principal = Depends(require_permission(REVIEW)),
    db: Session = Depends(get_session),
):
    return service.reject(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)
