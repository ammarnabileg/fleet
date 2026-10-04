from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.files import service as files
from app.modules.identity.service import Principal, get_principal
from app.modules.imports import schemas, service, sheets

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


@router.post("/imports/sheets/preview", response_model=schemas.PreviewOut)
def preview_sheets(file: UploadFile, _: Principal = Depends(_importer)):
    """A client's own workbook: its sheets, the first rows of each column, and the suggested kind and columns."""
    return sheets.preview(files.read_upload(file))


@router.post("/imports/sheets", response_model=schemas.ImportResult)
def import_sheets(
    file: UploadFile,
    plan: str = Form(...),
    apply: bool = False,
    principal: Principal = Depends(_importer),
    db: Session = Depends(get_session),
):
    """Imports the sheets as the plan says (JSON: company, sheets with their kind, first row and columns). Like the
    template: apply=false checks and changes nothing; apply=true imports a file without errors, all at once."""
    try:
        parsed = schemas.MappedPlan.model_validate_json(plan)
    except ValidationError as exc:
        raise AppError(422, "import_bad_mapping", sheet="-", fields=exc.errors()[0]["loc"][0]) from None
    return service.run_mapped(
        db,
        files.read_upload(file),
        parsed.model_dump(),
        apply=apply,
        actor_user_id=principal.user_id,
        can_set_salary=principal.has("employees.view_salary"),
        **principal.scope,
    )
