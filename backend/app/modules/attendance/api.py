import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.attendance import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.org import service as org

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


# ------------------------------------------------------------------ leave types


@router.get("/leave-types", response_model=list[schemas.LeaveTypeOut])
def leave_types(_: Principal = Depends(require_permission("leaves.view")), db: Session = Depends(get_session)):
    """The leave types and their rules: defaults read from the labour law, to review with HR/legal counsel."""
    return service.list_types(db)


@router.put("/leave-types/{code}", response_model=schemas.LeaveTypeOut)
def update_leave_type(
    code: str,
    body: schemas.LeaveTypeIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    changes = {
        k: v
        for k, v in body.model_dump(exclude={"version"}).items()
        if k in body.model_fields_set and (v is not None or k in schemas.NULLABLE_TYPE_FIELDS)
    }
    return service.update_type(db, code, changes, version=body.version, actor_user_id=principal.user_id)


@router.post("/leaves/preview", response_model=schemas.PreviewOut)
def preview(
    body: schemas.PreviewIn,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    """What the leave would count and pay, and the rules it breaks, before it is registered."""
    return service.preview(db, body.model_dump(), **principal.scope)


@router.get("/employees/{public_id}/leave-balances", response_model=list[schemas.BalanceOut])
def balances(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    return service.employee_balances(db, public_id, **principal.scope)


@router.get("/leaves/counts")
def counts(principal: Principal = Depends(require_permission("leaves.view")), db: Session = Depends(get_session)):
    return {"pending": service.pending_count(db, **principal.scope)}


@router.get("/leaves", response_model=list[schemas.LeaveOut])
def leaves(
    status: str | None = None,
    kind: str | None = None,
    source: str | None = None,
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
        kind=kind,
        source=source,
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
        db, public_id, approve=True, note=body.note, paid=body.paid, actor_user_id=principal.user_id, **principal.scope
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


@router.put("/leaves/{public_id}/followup-from", response_model=schemas.LeaveOut)
def followup_from(
    public_id: uuid.UUID,
    body: schemas.FollowupIn,
    principal: Principal = Depends(require_permission("leaves.approve")),
    db: Session = Depends(get_session),
):
    return service.set_followup_from(
        db, public_id, day=body.followup_from, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/leaves/{public_id}/followed-up", response_model=schemas.LeaveOut)
def followed_up(
    public_id: uuid.UUID,
    body: schemas.FollowedUpIn,
    principal: Principal = Depends(require_permission("leaves.view")),
    db: Session = Depends(get_session),
):
    """«تمت المتابعة»: the follow-up alert closes, and is not raised again for this request."""
    return service.mark_followed_up(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


# ------------------------------------------------------------------ the driver app

SCREEN = [Depends(org.screen("leaves"))]


@router.get("/driver/leaves", response_model=schemas.DriverLeavesOut, dependencies=SCREEN)
def my_leaves(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """The types he may request now (with what is left of each) and his last requests."""
    return service.driver_view(db, device.employee_id)


@router.post("/driver/leaves/preview", response_model=schemas.PreviewOut, dependencies=SCREEN)
def driver_preview(
    body: schemas.DriverPreviewIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.driver_preview(db, device.employee_id, body.model_dump())


@router.post("/driver/leaves", response_model=schemas.DriverLeaveOut, status_code=201, dependencies=SCREEN)
def driver_request(
    body: schemas.DriverLeaveIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.driver_request(
        db, employee_id=device.employee_id, device_id=device.device_id, data=body.model_dump()
    )


@router.post("/driver/leaves/{public_id}/cancel", response_model=schemas.DriverLeaveOut, dependencies=SCREEN)
def driver_cancel(
    public_id: uuid.UUID, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.driver_cancel(db, public_id, employee_id=device.employee_id)
