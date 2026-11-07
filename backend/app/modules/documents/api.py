import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.documents import schemas, service
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity.service import DevicePrincipal, Principal, get_principal, require_device, require_permission
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
    """Whose document it is comes from the owner's own module: a name for people, a plate for vehicles."""
    docs = service.list_expiring(db, within_days=within_days, **principal.scope)
    ids = {
        kind: {d["owner_db_id"] for d in docs if d["owner_type"] == kind} for kind in ("employee", "vehicle", "company")
    }
    staff = people.names(db, ids["employee"])
    cars = fleet.vehicles(db, ids["vehicle"])
    firms = {
        c["id"]: c for c in org.list_companies(db, all_companies=True, company_ids=[]) if c["id"] in ids["company"]
    }
    for d in docs:
        key = d.pop("owner_db_id")
        if d["owner_type"] == "employee" and key in staff:
            d["owner_id"], d["owner_name"] = staff[key]["id"], staff[key]["name"]
        elif d["owner_type"] == "vehicle" and key in cars:
            d["owner_id"], d["owner_name"] = str(cars[key].public_id), cars[key].plate_number
        elif d["owner_type"] == "company" and key in firms:
            d["owner_id"], d["owner_name"] = firms[key]["public_id"], firms[key]["name"]
    return docs


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
    side: Literal["front", "back"] = "front",
    principal: Principal = Depends(require_permission("documents.view")),
    db: Session = Depends(get_session),
):
    info = service.get_file(db, public_id, side=side, **principal.scope)
    return files.response(db, info)


# ---- the driver's documents (BRD FR-APP-05)


@router.get("/driver/documents", response_model=list[schemas.DriverDocumentOut])
def my_documents(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.driver_documents(db, device.employee_id)


@router.post("/driver/documents/renewals", response_model=schemas.RenewalOut, status_code=201)
def send_renewal(
    body: schemas.RenewalIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    driver = people.ref(db, device.employee_id)
    return service.submit_renewal(
        db,
        employee_id=driver.id,
        company_id=driver.company_id,
        device_id=device.device_id,
        driver_name=driver.name,
        data=body.model_dump(),
    )


@router.get("/documents/renewals", response_model=list[schemas.RenewalOut])
def renewals(
    status: str | None = "pending",
    principal: Principal = Depends(require_permission("documents.manage")),
    db: Session = Depends(get_session),
):
    return service.list_renewals(db, status=status, names_of=lambda ids: people.names(db, ids), **principal.scope)


@router.get("/documents/renewals/{public_id}/file")
def renewal_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("documents.manage")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.renewal_file(db, public_id, **principal.scope))


@router.post("/documents/renewals/{public_id}/{decision}", response_model=schemas.RenewalOut)
def decide_renewal(
    public_id: uuid.UUID,
    decision: Literal["approve", "reject"],
    body: schemas.DecisionIn,
    principal: Principal = Depends(require_permission("documents.manage")),
    db: Session = Depends(get_session),
):
    owner = None
    if decision == "approve":
        e = people.ref(db, service.renewal_employee_id(db, public_id, **principal.scope))
        owner = service.Owner("employee", e.id, str(e.public_id), e.company_id, e.name)
    return service.decide_renewal(
        db,
        public_id,
        approve=decision == "approve",
        note=body.note,
        owner=owner,
        actor_user_id=principal.user_id,
        **principal.scope,
    )
