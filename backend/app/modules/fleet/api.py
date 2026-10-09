import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from fastapi.responses import Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core import sheets
from app.core.clock import KUWAIT
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.files import service as files
from app.modules.fleet import schemas, service
from app.modules.i18n import service as i18n
from app.modules.identity.service import DevicePrincipal, Principal, require_device, require_permission
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["fleet"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _uuid(value: str, error: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise AppError(404, error) from None


# ---- vehicles


@router.get("/vehicles", response_model=list[schemas.VehicleOut])
def list_vehicles(
    company_id: int | None = None,
    status: str | None = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("vehicles.view")),
    db: Session = Depends(get_session),
):
    return service.list_vehicles(
        db, company_id=company_id, status=status, q=q, limit=limit, offset=offset, **principal.scope
    )


@router.get("/vehicles/{public_id}", response_model=schemas.VehicleOut)
def get_vehicle(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("vehicles.view")),
    db: Session = Depends(get_session),
):
    return service.get_vehicle(db, public_id, **principal.scope)


@router.post("/vehicles", response_model=schemas.VehicleOut, status_code=201)
def create_vehicle(
    body: schemas.VehicleIn,
    principal: Principal = Depends(require_permission("vehicles.create")),
    db: Session = Depends(get_session),
):
    return service.create_vehicle(db, body.model_dump(), actor_user_id=principal.user_id, **principal.scope)


@router.patch("/vehicles/{public_id}", response_model=schemas.VehicleOut)
def update_vehicle(
    public_id: uuid.UUID,
    body: schemas.VehicleUpdateIn,
    principal: Principal = Depends(require_permission("vehicles.update")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_vehicle(
        db, public_id, version=version, changes=changes, actor_user_id=principal.user_id, **principal.scope
    )


@router.get("/vehicles/{public_id}/custody-at", response_model=schemas.CustodyOut)
def custody_at(
    public_id: uuid.UUID,
    at: AwareDatetime,
    principal: Principal = Depends(require_permission("custody.view")),
    db: Session = Depends(get_session),
):
    """Who was responsible for the vehicle at a given moment (fines, accidents, damage)."""
    return service.custody_at(db, public_id, at, **principal.scope)


# ---- custody


@router.get("/custodies", response_model=list[schemas.CustodyOut])
def list_custodies(
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    open: bool = False,
    needs_review: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("custody.view")),
    db: Session = Depends(get_session),
):
    driver = people.ref_by_public_id(db, driver_id, **principal.scope).id if driver_id else None
    return service.list_custodies(
        db,
        vehicle_public_id=vehicle_id,
        driver_id=driver,
        open_only=open,
        needs_review=needs_review,
        limit=limit,
        offset=offset,
        **principal.scope,
    )


@router.get("/custodies/{public_id}", response_model=schemas.CustodyDetailOut)
def get_custody(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("custody.view")),
    db: Session = Depends(get_session),
):
    return service.get_custody(db, public_id, **principal.scope)


@router.post("/custodies", response_model=schemas.CustodyOut, status_code=201)
def handover(
    body: schemas.HandoverIn,
    principal: Principal = Depends(require_permission("custody.assign")),
    db: Session = Depends(get_session),
):
    return service.handover(
        db,
        vehicle_public_id=_uuid(body.vehicle_id, "vehicle_not_found"),
        driver_public_id=_uuid(body.driver_id, "employee_not_found"),
        odometer_km=body.odometer_km,
        photo_sha256=body.photo_sha256,
        started_at=body.started_at,
        kind=body.kind,
        reason=body.reason,
        can_emergency=principal.has("custody.emergency"),
        actor_user_id=principal.user_id,
        photos=[p.model_dump() for p in body.photos],
        **principal.scope,
    )


@router.post("/custodies/{public_id}/return", response_model=schemas.CustodyOut)
def return_vehicle(
    public_id: uuid.UUID,
    body: schemas.ReturnIn,
    principal: Principal = Depends(require_permission("custody.assign")),
    db: Session = Depends(get_session),
):
    return service.return_vehicle(
        db,
        public_id,
        odometer_km=body.odometer_km,
        photo_sha256=body.photo_sha256,
        ended_at=body.ended_at,
        actor_user_id=principal.user_id,
        photos=[p.model_dump() for p in body.photos],
        **principal.scope,
    )


@router.get("/custodies/{public_id}/photos/{sha256}")
def custody_photo(
    public_id: uuid.UUID,
    sha256: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    principal: Principal = Depends(require_permission("custody.view")),
    db: Session = Depends(get_session),
):
    info = service.custody_photo(db, public_id, sha256, **principal.scope)
    return files.response(db, info)


@router.post("/custodies/{public_id}/review", response_model=schemas.CustodyOut)
def review_custody(
    public_id: uuid.UUID,
    body: schemas.CustodyReviewIn,
    principal: Principal = Depends(require_permission("custody.emergency")),
    db: Session = Depends(get_session),
):
    return service.review_custody(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


# ---- odometer


@router.get("/odometer/readings", response_model=list[schemas.ReadingOut])
def list_readings(
    vehicle_id: uuid.UUID | None = None,
    review_status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("odometer.view")),
    db: Session = Depends(get_session),
):
    return service.list_readings(
        db, vehicle_public_id=vehicle_id, review_status=review_status, limit=limit, offset=offset, **principal.scope
    )


@router.post("/odometer/readings/{public_id}/review", response_model=schemas.ReadingOut)
def review_reading(
    public_id: uuid.UUID,
    body: schemas.ReadingReviewIn,
    principal: Principal = Depends(require_permission("odometer.review")),
    db: Session = Depends(get_session),
):
    return service.review_reading(
        db,
        public_id,
        corrected_km=body.corrected_km,
        reason=body.reason,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.get("/odometer/readings/{public_id}/photo")
def reading_photo(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("odometer.view")),
    db: Session = Depends(get_session),
):
    info = service.reading_photo(db, public_id, **principal.scope)
    return files.response(db, info)


# ---- driver app


@router.get("/driver/today", response_model=schemas.DriverTodayOut)
def driver_today(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.driver_today(db, device.employee_id)


@router.post("/driver/odometer", response_model=schemas.ReadingOut, status_code=201)
def driver_reading(
    body: schemas.DriverReadingIn,
    device: DevicePrincipal = Depends(require_device),
    db: Session = Depends(get_session),
):
    return service.driver_reading(
        db,
        employee_id=device.employee_id,
        device_id=device.device_id,
        kind=body.kind,
        value_km=body.value_km,
        photo_sha256=body.photo_sha256,
        recorded_at=body.recorded_at,
        lat=body.lat,
        lng=body.lng,
    )


# ---- "my car" and the change of vehicle the driver asks for (BRD FR-APP-02, FR-ASG-04)


@router.get("/driver/vehicle", response_model=schemas.MyVehicleOut)
def my_vehicle(device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)):
    return service.driver_vehicle(db, device.employee_id)


@router.post("/driver/vehicle-change-requests", response_model=schemas.MyVehicleOut, status_code=201)
def ask_vehicle_change(
    body: schemas.VehicleChangeIn, device: DevicePrincipal = Depends(require_device), db: Session = Depends(get_session)
):
    return service.request_vehicle_change(
        db,
        employee_id=device.employee_id,
        device_id=device.device_id,
        requested_plate=body.requested_plate,
        reason=body.reason,
    )


def _change_requests(db: Session, principal: Principal, status, driver_id, vehicle_id, limit=500, offset=0) -> list:
    return service.vehicle_change_requests(
        db,
        status=status or None,
        limit=limit,
        offset=offset,
        driver_id=people.ref_by_public_id(db, driver_id, **principal.scope).id if driver_id else None,
        vehicle_id=service.vehicle_ref_by_public_id(db, vehicle_id, **principal.scope).id if vehicle_id else None,
        **principal.scope,
    )


ChangeStatus = Literal["pending", "done", "rejected", "all", ""]


@router.get("/vehicle-change-requests", response_model=list[schemas.VehicleChangeOut])
def vehicle_change_requests(
    status: ChangeStatus = "pending",
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(require_permission("custody.view")),
    db: Session = Depends(get_session),
):
    """Pending (the default, oldest first), one status, or "all" (or empty) newest first; for a driver or a vehicle
    (the one he held or the one he asked for)."""
    return _change_requests(db, principal, status, driver_id, vehicle_id, limit, offset)


CHANGE_COLUMNS = (
    "created_at",
    "driver",
    "vehicle",
    "requested",
    "requested_now",
    "reason",
    "status",
    "decided_by",
    "decided_at",
    "note",
)


@router.get("/vehicle-change-requests/export")
def export_vehicle_change_requests(
    status: ChangeStatus = "all",
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    accept_language: str | None = Header(None),
    principal: Principal = Depends(require_permission("custody.view")),
    db: Session = Depends(get_session),
):
    """The same list in Excel, for the office's records."""
    rows = _change_requests(db, principal, status, driver_id, vehicle_id)
    lang = i18n.negotiate(db, principal.locale, accept_language)
    default = i18n.default_language(db).code

    def text(key: str, fallback: str) -> str:
        value = i18n.t(db, lang, key)
        return fallback if value == key else value

    def when(t) -> str:
        return t.astimezone(KUWAIT).strftime("%Y-%m-%d %H:%M") if t else ""

    def name(person) -> str:
        return i18n.pick(person["name"], lang, default) if person else ""

    def now(car) -> str:
        if not car or not car["found"]:
            return ""
        if car["holder"]:
            return i18n.t(db, lang, "change_column.with", name=name(car["holder"]))
        return text(f"vehicle_status.{car['status']}", car["status"])

    body = [
        [
            when(r["created_at"]),
            name(r["driver"]),
            r["vehicle_plate"] or "",
            r["requested_plate"],
            now(r["requested_vehicle"]),
            r["reason"],
            text(f"change_status.{r['status']}", r["status"]),
            r["decided_by"] or "",
            when(r["decided_at"]),
            r["note"] or "",
        ]
        for r in rows
    ]
    header = [text(f"change_column.{c}", c) for c in CHANGE_COLUMNS]
    content = sheets.to_xlsx(
        text("change_column.title", "requests"), header, body, rtl=lang == "ar", text_columns=(2, 3)
    )
    return Response(
        content, media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="vehicle-change-requests.xlsx"'}
    )


@router.post("/vehicle-change-requests/{public_id}/{decision}", response_model=schemas.VehicleChangeOut)
def close_vehicle_change(
    public_id: uuid.UUID,
    decision: Literal["done", "reject"],
    body: schemas.CloseChangeIn,
    principal: Principal = Depends(require_permission("custody.assign")),
    db: Session = Depends(get_session),
):
    return service.close_vehicle_change(
        db,
        public_id,
        done=decision == "done",
        note=body.note,
        actor_user_id=principal.user_id,
        **principal.scope,
    )
