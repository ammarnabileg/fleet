from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class PointIn(BaseModel):
    """Lenient on purpose: a bad point is rejected on its own (with a reason), never the whole batch,
    or one bad point would block the app's queue forever."""

    seq: int = Field(ge=0)
    recorded_at: AwareDatetime
    lat: float
    lng: float
    accuracy_m: float | None = None
    speed_kmh: float | None = None
    heading: int | None = Field(None, ge=0, le=360)
    is_mock: bool = False


class BatchIn(BaseModel):
    sent_at: AwareDatetime  # device clock when the batch was sent: corrects a wrong device clock
    points: list[PointIn] = Field(max_length=500)


class Rejected(BaseModel):
    seq: int
    reason: str


class BatchOut(BaseModel):
    stored_seqs: list[int]
    rejected: list[Rejected]
    server_time: datetime


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_permission: Literal["always", "while_in_use", "denied"] | None = None
    gps_enabled: bool | None = None
    battery_optimization_ignored: bool | None = None
    tracking_service_running: bool | None = None
    battery_level: int | None = Field(None, ge=0, le=100)
    queue_size: int | None = Field(None, ge=0)
    last_upload_at: AwareDatetime | None = None
    app_version: str | None = Field(None, max_length=30)


class HeartbeatOut(BaseModel):
    server_time: datetime
    tracking_required: bool
    interval_moving_s: int
    interval_stationary_s: int
    on_duty: bool = False  # day started and not ended
    company: dict[str, str] | None = None  # the driver's company name, by language


class VehicleRef(BaseModel):
    id: str
    plate_number: str


class DriverRef(BaseModel):
    id: str
    name: dict[str, str]


class LivePosition(BaseModel):
    lat: float
    lng: float
    speed_kmh: float | None
    heading: int | None
    recorded_at: datetime


class LiveVehicle(BaseModel):
    vehicle: VehicleRef
    driver: DriverRef | None
    custody_id: str
    company_id: int
    position: LivePosition | None
    signal_lost: bool
    on_duty: bool = True  # the driver's day started and not ended (BRD FR-TRK-09)
    position_hidden: bool = False  # off duty, and the user may not see it (tracking.off_duty)


class RoutePoint(BaseModel):
    t: datetime
    lat: float
    lng: float
    speed_kmh: float | None
    heading: int | None
    accuracy_m: float | None
    on_duty: bool = True  # within one of the driver's work days (BRD FR-TRK-09)


class RouteOut(BaseModel):
    vehicle: VehicleRef
    from_: datetime = Field(alias="from")
    to: datetime
    distance_km: float
    off_duty_km: float = 0  # between two points outside the work day
    hidden_off_duty: int = 0  # points outside the work day the user may not see (tracking.off_duty)
    truncated: bool
    drivers: list[DriverRef]
    points: list[RoutePoint]

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
