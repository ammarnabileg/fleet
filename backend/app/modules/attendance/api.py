import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.attendance import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import Principal, require_permission

router = APIRouter(prefix="/api/v1", tags=["attendance"])


@router.get("/attendance/days", response_model=schemas.ToClassifyOut)
def days_to_classify(
    date_from: date,
    date_to: date,
    employee_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    """The working drivers' days without a start of day or a daily report, for HR to mark (BRD BR-18)."""
    return service.to_classify(db, date_from=date_from, date_to=date_to, employee_id=employee_id, **principal.scope)


@router.post("/attendance/marks", response_model=schemas.MarkedOut)
def mark(
    body: schemas.MarkIn,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    n = service.mark_days(
        db,
        items=[(d.employee_id, d.day) for d in body.days],
        kind=body.kind,
        note=body.note,
        actor_user_id=principal.user_id,
        **principal.scope,
    )
    return {"marked": n}


@router.post("/attendance/marks/remove", status_code=204)
def unmark(
    body: schemas.DayRef,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    service.unmark_day(
        db, employee_id=body.employee_id, day=body.day, actor_user_id=principal.user_id, **principal.scope
    )
    return Response(status_code=204)


@router.get("/attendance/marks", response_model=list[schemas.MarkOut])
def marks(
    date_from: date,
    date_to: date,
    kind: str | None = None,
    employee_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    return service.list_marks(
        db, date_from=date_from, date_to=date_to, kind=kind, employee_id=employee_id, **principal.scope
    )


@router.get("/leaves", response_model=list[schemas.LeaveOut])
def leaves(
    status: str | None = None,
    employee_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    return service.list_leaves(
        db,
        status=status,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.post("/leaves", response_model=schemas.LeaveOut, status_code=201)
def create_leave(
    body: schemas.LeaveIn,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    data = body.model_dump(exclude={"approve"})
    return service.create_leave(db, data, approve=body.approve, actor_user_id=principal.user_id, **principal.scope)


@router.get("/leaves/{public_id}", response_model=schemas.LeaveOut)
def get_leave(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    return service.get_leave(db, public_id, **principal.scope)


@router.get("/leaves/{public_id}/file")
def leave_file(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    return files.response(db, service.leave_file(db, public_id, **principal.scope))


@router.post("/leaves/{public_id}/approve", response_model=schemas.LeaveOut)
def approve(
    public_id: uuid.UUID,
    body: schemas.ApproveIn,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_leave(
        db, public_id, approve=True, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/leaves/{public_id}/reject", response_model=schemas.LeaveOut)
def reject(
    public_id: uuid.UUID,
    body: schemas.RejectIn,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    return service.decide_leave(
        db, public_id, approve=False, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/leaves/{public_id}/cancel", response_model=schemas.LeaveOut)
def cancel(
    public_id: uuid.UUID,
    body: schemas.CancelIn,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    return service.cancel_leave(db, public_id, reason=body.reason, actor_user_id=principal.user_id, **principal.scope)
