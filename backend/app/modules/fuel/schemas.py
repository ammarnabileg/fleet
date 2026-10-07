import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

FuelType = Literal["premium_91", "super_95", "ultra_98", "diesel"]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class _Fill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filled_at: AwareDatetime
    litres: Annotated[Decimal, Field(gt=0, le=1000, max_digits=7, decimal_places=2)]
    amount: Annotated[Decimal, Field(gt=0, le=10000, max_digits=10, decimal_places=3)]
    fuel_type: FuelType
    station: Text | None = None
    odometer_km: int = Field(ge=0, le=5_000_000)
    invoice_sha256: Sha
    odometer_sha256: Sha | None = None


class DriverFillIn(_Fill):
    odometer_sha256: Sha  # the app's camera photo of the odometer, always


class OfficeFillIn(_Fill):
    vehicle_id: uuid.UUID


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Reason


class FillOut(BaseModel):
    id: str
    number: int
    vehicle: dict
    company_id: int
    driver: dict | None
    filled_at: datetime
    business_date: date
    litres: Decimal
    amount: Decimal
    fuel_type: str
    station: str | None
    odometer_km: int
    invoice_sha256: str
    odometer_sha256: str | None
    source: str
    price: Decimal | None
    expected_amount: Decimal | None
    flags: list[str]
    km_since: int | None
    litres_per_100km: Decimal | None
    status: str
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_by: str | None
    created_at: datetime


class DriverFuelOut(BaseModel):
    vehicle: dict | None
    fills: list[dict]


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fuel_type: FuelType
    price: Annotated[Decimal, Field(gt=0, le=10, max_digits=8, decimal_places=3)]
    effective_from: date


class PricesOut(BaseModel):
    current: dict[str, Decimal | None]
    history: list[dict]


class ModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    make: Text
    model: Text
    tank_litres: Annotated[Decimal, Field(gt=0, le=500, max_digits=6, decimal_places=1)]
    fuel_types: list[FuelType] = Field(min_length=1, max_length=4)
    litres_per_100km: Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
    version: int | None = None


class ModelOut(BaseModel):
    id: int
    make: str
    model: str
    tank_litres: Decimal
    fuel_types: list[str]
    litres_per_100km: Decimal
    version: int


class ConsumptionRow(BaseModel):
    vehicle: dict
    fills: int
    litres: Decimal
    amount: Decimal
    km: int
    litres_per_100km: Decimal | None
    reference: Decimal | None
    over_percent: Decimal | None
    over: bool
