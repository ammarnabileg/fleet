from typing import Literal

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.files import schemas, service
from app.modules.identity.service import DevicePrincipal, Principal, get_principal, require_device

router = APIRouter(prefix="/api/v1", tags=["files"])

UPLOADERS = (
    "documents.manage",
    "custody.assign",
    "odometer.review",
    "maintenance.create",
    "invoices.create",
    "accidents.create",  # accident photos and the police report
    "accidents.update",
    "fines.manage",  # a scan of the ticket
    "portal.vehicles",  # maintenance centers: reception and repair photos
    "portal.quotes",
    "portal.invoices",
    "portal.damage",  # the damage estimate and its photos
)


@router.post("/files", response_model=schemas.FileOut, status_code=201)
def upload(file: UploadFile, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    """Office uploads (document scans, handover photos). The returned sha256 is then attached to a record."""
    if not any(principal.has(p) for p in UPLOADERS):
        raise AppError(403, "permission_denied", permission=" | ".join(UPLOADERS))
    info = service.store(db, service.read_upload(file), source="upload", uploaded_by_user=principal.user_id)
    db.commit()
    return info.__dict__


@router.post("/driver/files", response_model=schemas.FileOut, status_code=201)
def driver_upload(
    file: UploadFile,
    source: Literal["camera", "upload"] = "camera",
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    """From the driver app. "camera": taken in the app (odometer and vehicle photos accept only these, from the
    same device). "upload": picked from the phone (document scans), image or PDF."""
    info = service.store(
        db,
        service.read_upload(file),
        source=source,
        uploaded_by_device=device.device_id,
        images_only=source == "camera",
    )
    db.commit()
    return info.__dict__
