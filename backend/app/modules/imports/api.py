from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.files import service as files
from app.modules.identity.service import Principal, get_principal
from app.modules.imports import schemas, service

router = APIRouter(prefix="/api/v1", tags=["imports"])
NEEDED = ("employees.create", "employees.update", "vehicles.create", "vehicles.update", "documents.manage")


def _importer(principal: Principal = Depends(get_principal)) -> Principal:
    missing = [p for p in NEEDED if not principal.has(p)]
    if missing:
        raise AppError(403, "permission_denied", permission=", ".join(missing))
    return principal


@router.post("/imports/workbook", response_model=schemas.ImportResult)
def import_workbook(
    file: UploadFile,
    apply: bool = False,
    principal: Principal = Depends(_importer),
    db: Session = Depends(get_session),
):
    """The onboarding workbook (vehicles, users and drivers). apply=false checks it and changes nothing; apply=true
    imports a file without errors, all at once. The same file can be imported again: it updates."""
    return service.run(
        db,
        files.read_upload(file),
        apply=apply,
        actor_user_id=principal.user_id,
        can_set_salary=principal.has("employees.view_salary"),
        can_open=principal.has("cash.adjust"),
        **principal.scope,
    )
