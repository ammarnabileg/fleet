from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.files import schemas, service
from app.modules.identity.service import DevicePrincipal, Principal, get_principal, require_device

router = APIRouter(prefix="/api/v1", tags=["files"])

UPLOADERS = ("documents.manage", "custody.assign", "odometer.review")


def read_limited(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, "file_too_large", max_mb=get_settings().max_upload_mb)
    return data


@router.post("/files", response_model=schemas.FileOut, status_code=201)
def upload(file: UploadFile, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    """Office uploads (document scans, handover photos). The returned sha256 is then attached to a record."""
    if not any(principal.has(p) for p in UPLOADERS):
        raise AppError(403, "permission_denied", permission=" | ".join(UPLOADERS))
    info = service.store(db, read_limited(file), source="upload", uploaded_by_user=principal.user_id)
    db.commit()
    return info.__dict__


@router.post("/driver/files", response_model=schemas.FileOut, status_code=201)
def driver_upload(
    file: UploadFile, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    """Photos from the driver app's camera (odometer). The app has no gallery picker; the server records the
    device, and readings accept only photos uploaded by the same device through this endpoint."""
    info = service.store(db, read_limited(file), source="camera", uploaded_by_device=device.device_id, images_only=True)
    db.commit()
    return info.__dict__
