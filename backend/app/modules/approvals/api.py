import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.modules.approvals import schemas, service
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.identity.service import Principal, require_permission

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])

view = require_permission("approvals.view")
configure = require_permission("approvals.workflows")


# ---- the workflows (who configures them)


@router.get("/workflows", response_model=list[schemas.WorkflowOut])
def workflows(_: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.list_workflows(db)


@router.put("/workflows/{process}", response_model=schemas.WorkflowOut)
def set_workflow(
    process: schemas.Process,
    body: schemas.WorkflowIn,
    principal: Principal = Depends(configure),
    db: Session = Depends(get_session),
):
    for step in body.steps:
        i18n.validate_localized(db, step.name)
    return service.set_workflow(
        db,
        process,
        active=body.active,
        steps=[s.model_dump() for s in body.steps],
        version=body.version,
        actor_user_id=principal.user_id,
    )


@router.get("/options", response_model=schemas.OptionsOut)
def options(_: Principal = Depends(configure), db: Session = Depends(get_session)):
    return service.options(db)


# ---- the inbox, the decisions, a document's history


@router.get("/inbox", response_model=list[schemas.RequestOut])
def inbox(principal: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.inbox(db, actor_user_id=principal.user_id, **principal.scope)


@router.post("/requests/{public_id}/decide", response_model=schemas.RequestOut)
def decide(
    public_id: uuid.UUID,
    body: schemas.DecideIn,
    principal: Principal = Depends(view),
    db: Session = Depends(get_session),
):
    return service.decide(
        db, public_id, approve=body.approve, reason=body.reason, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/history/{process}/{document_id}", response_model=list[schemas.RequestOut])
def history(
    process: schemas.Process,
    document_id: uuid.UUID,
    principal: Principal = Depends(view),
    db: Session = Depends(get_session),
):
    return service.history(db, process, document_id, **principal.scope)


# ---- delegation while away


@router.get("/delegations", response_model=list[schemas.DelegationOut])
def delegations(principal: Principal = Depends(view), db: Session = Depends(get_session)):
    manager = principal.has("approvals.workflows")
    return service.list_delegations(db, user_id=None if manager else principal.user_id)


@router.post("/delegations", response_model=schemas.DelegationOut, status_code=201)
def add_delegation(
    body: schemas.DelegationIn, principal: Principal = Depends(view), db: Session = Depends(get_session)
):
    user_id = principal.user_id
    if body.user_id is not None and str(body.user_id) != principal.public_id:
        if not principal.has("approvals.workflows"):
            raise AppError(403, "permission_denied", permission="approvals.workflows")
        user_id = identity.user_id(db, body.user_id)
    return service.add_delegation(
        db,
        user_id=user_id,
        delegate_public_id=body.delegate_id,
        date_from=body.date_from,
        date_to=body.date_to,
        reason=body.reason,
        actor_user_id=principal.user_id,
    )


@router.post("/delegations/{public_id}/cancel", response_model=schemas.DelegationOut)
def cancel_delegation(public_id: uuid.UUID, principal: Principal = Depends(view), db: Session = Depends(get_session)):
    return service.cancel_delegation(
        db, public_id, actor_user_id=principal.user_id, manager=principal.has("approvals.workflows")
    )


@router.get("/people", response_model=list[schemas.Ref])
def people(_: Principal = Depends(view), db: Session = Depends(get_session)):
    """Whom a delegation may name."""
    return identity.user_options(db)
