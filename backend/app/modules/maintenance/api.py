import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.maintenance import schemas, service

router = APIRouter(prefix="/api/v1", tags=["maintenance"])

Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


# ------------------------------------------------------------------ centers (office)


@router.get("/maintenance/centers", response_model=list[schemas.CenterOut])
def list_centers(
    active: bool = False,
    principal: Principal = Depends(require_permission("maintenance.view")),
    db: Session = Depends(get_session),
):
    """Every holder of maintenance.view needs the list to refer a vehicle; managing them is separate."""
    return service.list_centers(db, active_only=active)


@router.post("/maintenance/centers", response_model=schemas.CenterOut, status_code=201)
def create_center(
    body: schemas.CenterIn,
    principal: Principal = Depends(require_permission("maintenance_centers.manage")),
    db: Session = Depends(get_session),
):
    return service.create_center(db, body.model_dump(), actor_user_id=principal.user_id)


@router.put("/maintenance/centers/{public_id}", response_model=schemas.CenterOut)
def update_center(
    public_id: uuid.UUID,
    body: schemas.CenterUpdateIn,
    principal: Principal = Depends(require_permission("maintenance_centers.manage")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    return service.update_center(db, public_id, version=body.version, changes=changes, actor_user_id=principal.user_id)


@router.get("/maintenance/centers/{public_id}/users", response_model=list[schemas.PortalUserOut])
def center_users(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("maintenance_centers.view")),
    db: Session = Depends(get_session),
):
    return service.center_users(db, public_id)


@router.post("/maintenance/centers/{public_id}/users", response_model=list[schemas.PortalUserOut], status_code=201)
def add_center_user(
    public_id: uuid.UUID,
    body: schemas.PortalUserIn,
    principal: Principal = Depends(require_permission("maintenance_centers.manage")),
    db: Session = Depends(get_session),
):
    return service.add_center_user(db, public_id, body.model_dump(), actor_user_id=principal.user_id)


@router.put("/maintenance/centers/{public_id}/users/{user_id}", response_model=list[schemas.PortalUserOut])
def set_center_user_active(
    public_id: uuid.UUID,
    user_id: uuid.UUID,
    body: schemas.PortalUserActiveIn,
    principal: Principal = Depends(require_permission("maintenance_centers.manage")),
    db: Session = Depends(get_session),
):
    return service.set_center_user_active(
        db, public_id, user_id, active=body.is_active, actor_user_id=principal.user_id
    )


# ------------------------------------------------------------------ requests (office)


@router.get("/maintenance/requests", response_model=list[schemas.RequestOut])
def list_requests(
    status: str | None = None,
    active: bool | None = None,
    vehicle_id: uuid.UUID | None = None,
    center_id: uuid.UUID | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
    principal: Principal = Depends(require_permission("maintenance.view")),
    db: Session = Depends(get_session),
):
    return service.list_requests(
        db,
        status=status,
        active=active,
        vehicle_public_id=vehicle_id,
        center_public_id=center_id,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/maintenance/requests", response_model=schemas.RequestDetailOut, status_code=201)
def create_request(
    body: schemas.RequestIn,
    principal: Principal = Depends(require_permission("maintenance.create")),
    db: Session = Depends(get_session),
):
    return service.create_request(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.get("/maintenance/requests/{public_id}", response_model=schemas.RequestDetailOut)
def get_request(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("maintenance.view")),
    db: Session = Depends(get_session),
):
    return service.get_request(db, public_id, **principal.scope)


@router.get("/maintenance/requests/{public_id}/files/{sha256}")
def request_file(
    public_id: uuid.UUID,
    sha256: str,
    principal: Principal = Depends(require_permission("maintenance.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.request_file(db, public_id, sha256, **principal.scope))


@router.post("/maintenance/requests/{public_id}/approve", response_model=schemas.RequestDetailOut)
def approve(
    public_id: uuid.UUID,
    body: schemas.NoteIn,
    principal: Principal = Depends(require_permission("maintenance.approve")),
    db: Session = Depends(get_session),
):
    return service.approve(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


@router.post("/maintenance/requests/{public_id}/reject", response_model=schemas.RequestDetailOut)
def reject(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("maintenance.approve")),
    db: Session = Depends(get_session),
):
    return service.reject(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/maintenance/requests/{public_id}/review-emergency", response_model=schemas.RequestDetailOut)
def review_emergency(
    public_id: uuid.UUID,
    body: schemas.NoteIn,
    principal: Principal = Depends(require_permission("maintenance.approve")),
    db: Session = Depends(get_session),
):
    return service.review_emergency(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


@router.post("/maintenance/requests/{public_id}/refer", response_model=schemas.RequestDetailOut)
def refer(
    public_id: uuid.UUID,
    body: schemas.ReferIn,
    principal: Principal = Depends(require_permission("maintenance.approve")),
    db: Session = Depends(get_session),
):
    return service.refer(
        db,
        public_id,
        center_public_id=body.center_id,
        note=body.note,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/maintenance/requests/{public_id}/cancel", response_model=schemas.RequestDetailOut)
def cancel(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("maintenance.create")),
    db: Session = Depends(get_session),
):
    return service.cancel(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)


@router.post("/maintenance/requests/{public_id}/picked-up", response_model=schemas.RequestDetailOut)
def picked_up(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("maintenance.create")),
    db: Session = Depends(get_session),
):
    return service.picked_up(db, public_id, actor_user_id=principal.user_id, **principal.scope)


@router.post("/maintenance/quotes/{public_id}/approve", response_model=schemas.RequestDetailOut)
def approve_quote(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("maintenance.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_quote(
        db, public_id, approve=True, reason=None, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/maintenance/quotes/{public_id}/reject", response_model=schemas.RequestDetailOut)
def reject_quote(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("maintenance.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_quote(
        db, public_id, approve=False, reason=body.reason, actor_user_id=principal.user_id, **principal.scope
    )


# ------------------------------------------------------------------ invoices (office)


@router.get("/maintenance/invoices", response_model=list[schemas.InvoiceOut])
def list_invoices(
    status: str | None = None,
    payment_status: str | None = None,
    center_id: uuid.UUID | None = None,
    limit: Limit = 100,
    offset: Offset = 0,
    principal: Principal = Depends(require_permission("invoices.view")),
    db: Session = Depends(get_session),
):
    return service.list_invoices(
        db,
        status=status,
        payment_status=payment_status,
        center_public_id=center_id,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/maintenance/invoices", response_model=schemas.InvoiceOut, status_code=201)
def office_invoice(
    body: schemas.OfficeInvoiceIn,
    principal: Principal = Depends(require_permission("invoices.create")),
    db: Session = Depends(get_session),
):
    return service.office_invoice(db, actor_user_id=principal.user_id, data=body.model_dump(), **principal.scope)


@router.get("/maintenance/invoices/{public_id}/file")
def invoice_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("invoices.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.invoice_file(db, public_id, **principal.scope))


@router.post("/maintenance/invoices/{public_id}/approve", response_model=schemas.InvoiceOut)
def approve_invoice(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("invoices.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_invoice(
        db, public_id, approve=True, reason=None, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/maintenance/invoices/{public_id}/reject", response_model=schemas.InvoiceOut)
def reject_invoice(
    public_id: uuid.UUID,
    body: schemas.ReasonIn,
    principal: Principal = Depends(require_permission("invoices.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_invoice(
        db, public_id, approve=False, reason=body.reason, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/maintenance/invoices/{public_id}/paid", response_model=schemas.InvoiceOut)
def mark_paid(
    public_id: uuid.UUID,
    body: schemas.PaidIn,
    principal: Principal = Depends(require_permission("finance.create")),
    db: Session = Depends(get_session),
):
    """Paying a center is a finance action (the accountant), separate from approving the invoice."""
    return service.mark_paid(
        db, public_id, payment_ref=body.payment_ref, actor_user_id=principal.user_id, **principal.scope
    )


# ------------------------------------------------------------------ the center's portal (its own vehicles only)


@router.get("/portal/me")
def portal_me(
    principal: Principal = Depends(require_permission("portal.vehicles")), db: Session = Depends(get_session)
):
    return service.portal_center(db, user_id=principal.user_id)


@router.get("/portal/requests", response_model=list[schemas.RequestOut])
def portal_requests(
    active: bool = True,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.portal_requests(db, user_id=principal.user_id, active=active)


@router.get("/portal/requests/{public_id}", response_model=schemas.RequestDetailOut)
def portal_request(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.portal_request(db, public_id, user_id=principal.user_id)


@router.get("/portal/requests/{public_id}/files/{sha256}")
def portal_file(
    public_id: uuid.UUID,
    sha256: str,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.portal_file(db, public_id, sha256, user_id=principal.user_id))


@router.post("/portal/requests/{public_id}/receive", response_model=schemas.RequestDetailOut)
def receive(
    public_id: uuid.UUID,
    body: schemas.ReceiveIn,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.receive(db, public_id, user_id=principal.user_id, data=body.model_dump())


@router.post("/portal/requests/{public_id}/status", response_model=schemas.RequestDetailOut)
def set_status(
    public_id: uuid.UUID,
    body: schemas.StatusIn,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.set_status(db, public_id, user_id=principal.user_id, status=body.status, note=body.note)


@router.post("/portal/requests/{public_id}/quote", response_model=schemas.RequestDetailOut)
def submit_quote(
    public_id: uuid.UUID,
    body: schemas.QuoteIn,
    principal: Principal = Depends(require_permission("portal.quotes")),
    db: Session = Depends(get_session),
):
    return service.submit_quote(db, public_id, user_id=principal.user_id, data=body.model_dump())


@router.post("/portal/requests/{public_id}/complete", response_model=schemas.RequestDetailOut)
def complete(
    public_id: uuid.UUID,
    body: schemas.CompleteIn,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.complete(db, public_id, user_id=principal.user_id, data=body.model_dump())


@router.post("/portal/requests/{public_id}/ready", response_model=schemas.RequestDetailOut)
def ready(
    public_id: uuid.UUID,
    body: schemas.NoteIn,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.ready(db, public_id, user_id=principal.user_id, note=body.note)


@router.post("/portal/requests/{public_id}/picked-up", response_model=schemas.RequestDetailOut)
def portal_picked_up(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("portal.vehicles")),
    db: Session = Depends(get_session),
):
    return service.portal_picked_up(db, public_id, user_id=principal.user_id)


@router.get("/portal/invoices", response_model=list[schemas.InvoiceOut])
def portal_invoices(
    principal: Principal = Depends(require_permission("portal.invoices")), db: Session = Depends(get_session)
):
    return service.portal_invoices(db, user_id=principal.user_id)


@router.post("/portal/invoices", response_model=schemas.InvoiceOut, status_code=201)
def portal_invoice(
    body: schemas.InvoiceIn,
    principal: Principal = Depends(require_permission("portal.invoices")),
    db: Session = Depends(get_session),
):
    return service.portal_invoice(db, user_id=principal.user_id, data=body.model_dump())


@router.get("/portal/invoices/{public_id}/file")
def portal_invoice_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("portal.invoices")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.portal_invoice_file(db, public_id, user_id=principal.user_id))


# ------------------------------------------------------------------ the driver app


@router.post("/driver/maintenance", response_model=schemas.DriverRequestOut, status_code=201)
def driver_request(
    body: schemas.DriverRequestIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.driver_request(
        db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump()
    )


@router.get("/driver/maintenance", response_model=list[schemas.DriverRequestOut])
def my_requests(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.for_driver(db, device.employee_id)
