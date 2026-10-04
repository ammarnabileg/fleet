import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.documents import schemas, service
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity.service import Principal, get_principal, require_permission
from app.modules.org import service as org
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["documents"])


def resolve_owner(db: Session, owner_type: str, owner_id: str, principal: Principal) -> service.Owner:
    """The owner through its own module, with that module's company scope (out of scope = not found)."""
    try:
        public_id = uuid.UUID(owner_id)
    except ValueError:
        raise AppError(404, "owner_not_found") from None
    try:
        if owner_type == "employee":
            e = people.ref_by_public_id(db, public_id, **principal.scope)
            return service.Owner("employee", e.id, str(e.public_id), e.company_id, e.name)
        if owner_type == "vehicle":
            v = fleet.vehicle_ref_by_public_id(db, public_id, **principal.scope)
            return service.Owner("vehicle", v.id, str(v.public_id), v.company_id, v.plate_number)
        c = org.get_company(db, public_id, **principal.scope)
        return service.Owner("company", c["id"], c["public_id"], c["id"], c["name"])
    except AppError as exc:
        if exc.status == 404:
            raise AppError(404, "owner_not_found") from None
        raise


@router.get("/document-types", response_model=list[schemas.DocumentTypeOut])
def list_types(_: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return service.list_types(db)


@router.get("/documents", response_model=list[schemas.DocumentOut])
def list_documents(
    owner_type: schemas.OwnerType,
    owner_id: str,
    history: bool = False,
    principal: Principal = Depends(require_permission("documents.view")),
    db: Session = Depends(get_session),
):
    owner = resolve_owner(db, owner_type, owner_id, principal)
    return service.list_for_owner(db, owner, include_history=history)


@router.get("/documents/expiring", response_model=list[schemas.DocumentOut])
def list_expiring(
    within_days: Annotated[int, Query(ge=0, le=365)] = 30,
    principal: Principal = Depends(require_permission("documents.view")),
    db: Session = Depends(get_session),
):
    return service.list_expiring(db, within_days=within_days, **principal.scope)


@router.post("/documents", response_model=schemas.DocumentOut, status_code=201)
def add_document(
    body: schemas.DocumentIn,
    principal: Principal = Depends(require_permission("documents.manage")),
    db: Session = Depends(get_session),
):
    owner = resolve_owner(db, body.owner_type, body.owner_id, principal)
    return service.add(db, owner, body.model_dump(exclude={"owner_type", "owner_id"}), actor_user_id=principal.user_id)


@router.get("/documents/{public_id}/file")
def document_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("documents.view")),
    db: Session = Depends(get_session),
):
    info = service.get_file(db, public_id, **principal.scope)
    return FileResponse(
        files.path_of(info.sha256),
        media_type=info.content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
