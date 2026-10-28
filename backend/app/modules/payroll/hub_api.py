"""The contracted platforms section: each platform's overview, its drivers with their ID on it, removing a platform
added by hand, and the drivers' requests from the app to be put on a platform (the office approves or rejects)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.payroll import platform_requests, platforms, rider_ids
from app.modules.payroll.schemas import DriverSchemeOut
from app.modules.payroll.service import month_start

router = APIRouter(prefix="/api/v1", tags=["platforms"])
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class DriverIdIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform_driver_id: Short | None = None  # empty: cleared


class RiderIdIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: date
    rider_id: Short | None = None  # empty: none this month


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform_id: int
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    scheme_id: uuid.UUID | None = None  # the scheme he picks with it (one the company offers)


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int | None = None
    platform_id: int | None = None  # the office may correct the company he picked
    platform_driver_id: Short | None = None


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int | None = None
    note: Note


@router.delete("/payroll/platforms/{platform_id}", status_code=204)
def delete_platform(
    platform_id: int,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    """A platform added by hand and never used; the core platforms are never removed (409 platform_core)."""
    platforms.delete(db, platform_id, actor_user_id=principal.user_id)
    return Response(status_code=204)


@router.get("/payroll/platforms/{platform_id}/overview")
def platform_overview(
    platform_id: int,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return platforms.overview(db, platform_id, **principal.scope)


@router.get("/payroll/platforms/{platform_id}/drivers")
def platform_drivers(
    platform_id: int,
    missing: bool = False,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    """The platform's drivers with their ID on it; missing=true: those without one."""
    return platforms.drivers(db, platform_id, missing=missing, **principal.scope)


@router.put("/payroll/platforms/{platform_id}/drivers/{employee_id}")
def set_platform_driver_id(
    platform_id: int,
    employee_id: uuid.UUID,
    body: DriverIdIn,
    principal: Principal = Depends(require_permission("employees.update")),
    db: Session = Depends(get_session),
):
    return platforms.set_driver_id(
        db,
        platform_id,
        employee_id,
        value=body.platform_driver_id,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.get("/payroll/platforms/{platform_id}/rider-ids")
def rider_id_month(
    platform_id: int,
    month: date,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    """Each driver's ID on the platform that month, and last month's (an ID may move to another employee)."""
    platforms._platform(db, platform_id)
    return rider_ids.month_table(db, platform_id, month_start(month), **principal.scope)


@router.put("/payroll/platforms/{platform_id}/rider-ids/{employee_id}")
def set_rider_id(
    platform_id: int,
    employee_id: uuid.UUID,
    body: RiderIdIn,
    principal: Principal = Depends(require_permission("employees.update")),
    db: Session = Depends(get_session),
):
    """He works this ID that month; whoever had it that month loses it."""
    platforms._platform(db, platform_id)
    return rider_ids.set_id(db, platform_id, month_start(body.month), employee_id, value=body.rider_id,
                            actor_user_id=principal.user_id, **principal.scope)  # fmt: skip


# ------------------------------------------------------------------ the drivers' requests


@router.get("/payroll/platform-requests")
def list_platform_requests(
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
    platform_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return platform_requests.list_requests(
        db, status=status, platform_id=platform_id, limit=limit, offset=offset, **principal.scope
    )


@router.get("/payroll/platform-requests/counts")
def platform_request_counts(
    principal: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return platform_requests.counts(db, **principal.scope)


@router.post("/payroll/platform-requests/{public_id}/approve")
def approve_platform_request(
    public_id: uuid.UUID,
    body: ApproveIn,
    principal: Principal = Depends(require_permission("employees.update")),
    db: Session = Depends(get_session),
):
    return platform_requests.approve(
        db,
        public_id,
        version=body.version,
        platform_id=body.platform_id,
        platform_driver_id=body.platform_driver_id,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/payroll/platform-requests/{public_id}/reject")
def reject_platform_request(
    public_id: uuid.UUID,
    body: RejectIn,
    principal: Principal = Depends(require_permission("employees.update")),
    db: Session = Depends(get_session),
):
    return platform_requests.reject(
        db, public_id, version=body.version, note=body.note, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/driver/platform-request")
def my_platform(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    """His company (set by the office), those he may pick, his latest request; ask: the company screen is due."""
    return platform_requests.driver_view(db, device.employee_id)


@router.post("/driver/platform-request", status_code=201)
def ask_platform(body: AskIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return platform_requests.ask(
        db,
        device.employee_id,
        device_id=device.device_id,
        platform_id=body.platform_id,
        note=body.note,
        scheme_public_id=body.scheme_id,
    )


@router.get("/driver/platform-request/{platform_id}/schemes", response_model=list[DriverSchemeOut])
def platform_schemes(
    platform_id: int, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    """The schemes of a company he is about to pick, with their terms: he picks one with it."""
    return platform_requests.offered_schemes(db, device.employee_id, platform_id)


@router.post("/driver/platform-request/{public_id}/cancel")
def cancel_platform_request(
    public_id: uuid.UUID, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return platform_requests.cancel(db, device.employee_id, public_id)
