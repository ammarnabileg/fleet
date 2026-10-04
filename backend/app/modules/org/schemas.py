import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

Money = Field(ge=0, max_digits=12, decimal_places=3)


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- settings sections: product defaults here, each client's values live in the database (section 13)


class TrackingSettings(_Section):
    interval_moving_s: int = Field(30, ge=5, le=600)
    interval_stationary_s: int = Field(300, ge=30, le=3600)
    signal_loss_minutes: int = Field(10, ge=1, le=240)


class CashSettings(_Section):
    driver_balance_alert: Decimal = Field(Decimal("80.000"), ge=0, max_digits=12, decimal_places=3)
    report_review_hours: int = Field(24, ge=1, le=168)


class OdometerSettings(_Section):
    daily_km_alert: int = Field(400, ge=1, le=2000)
    off_duty_km_alert: int = Field(5, ge=0, le=500)


class DocumentSettings(_Section):
    expiry_alert_days: int = Field(30, ge=1, le=365)
    commercial_license_alert_days: int = Field(60, ge=1, le=365)


class MaintenanceSettings(_Section):
    approval_limit: Decimal = Field(Decimal("100.000"), ge=0, max_digits=12, decimal_places=3)


class PayrollSettings(_Section):
    max_monthly_deduction: Decimal | None = Field(
        None, ge=0, max_digits=12, decimal_places=3
    )  # required before payroll runs


class DailyReportSettings(_Section):
    require_orders_count: bool = True
    require_cash: bool = True
    require_screenshot: bool = True


class BrandingSettings(_Section):
    display_name: str = Field("BrilliantTech Fleet", min_length=2, max_length=60)
    primary_color: str = Field("#0A6CFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_file: str | None = Field(None, max_length=64)


SECTIONS: dict[str, type[_Section]] = {
    "tracking": TrackingSettings,
    "cash": CashSettings,
    "odometer": OdometerSettings,
    "documents": DocumentSettings,
    "maintenance": MaintenanceSettings,
    "payroll": PayrollSettings,
    "daily_report": DailyReportSettings,
    "branding": BrandingSettings,
}


class SettingOut(BaseModel):
    version: int
    value: dict


class SettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)  # 0 = the section was never saved (defaults)
    value: dict


# ---- companies & branches


class CompanyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_ar: str = Field(min_length=2, max_length=150)
    name_en: str = Field(min_length=2, max_length=150)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    name_ar: str
    name_en: str
    is_active: bool


class BranchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_public_id: uuid.UUID
    name_ar: str = Field(min_length=2, max_length=150)
    name_en: str = Field(min_length=2, max_length=150)


class BranchUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name_ar: str | None = Field(default=None, min_length=2, max_length=150)
    name_en: str | None = Field(default=None, min_length=2, max_length=150)
    is_active: bool | None = None


class BranchOut(BaseModel):
    id: int
    public_id: str
    company_public_id: str
    name_ar: str
    name_en: str
    is_active: bool
    version: int
