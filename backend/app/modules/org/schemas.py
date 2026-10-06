from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import LocalizedText

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


DOC_CODE = r"^[a-z][a-z0-9_]{1,30}$"


class OnboardingSettings(_Section):
    """What a driver must send in self-registration (document types from the documents module)."""

    required_documents: list[Annotated[str, StringConstraints(pattern=DOC_CODE)]] = Field(
        default_factory=lambda: ["residence", "driving_license", "passport"], max_length=10
    )
    vehicle_photos: list[Literal["front", "back", "left", "right", "interior"]] = Field(
        default_factory=lambda: ["front", "back", "left", "right"], max_length=5
    )
    require_bank: bool = True  # the IBAN and the bank name (salaries are paid by transfer)


class MessagingSettings(_Section):
    """Bulk WhatsApp sending (activation links): spaced out and within the day, so the number is not flagged as spam."""

    bulk_interval_seconds: int = Field(60, ge=10, le=3600)
    bulk_daily_limit: int = Field(100, ge=1, le=1000)
    send_from_hour: int = Field(8, ge=0, le=23)  # Kuwait time
    send_until_hour: int = Field(22, ge=1, le=24)


class DriverSignInSettings(_Section):
    """How a driver's phone is trusted. With phone codes on, a WhatsApp code to the phone binds it and a driver signs
    in with his phone. Off, for a client whose drivers' numbers change hands (the office hands the SIMs out), the code
    would prove nothing and would let next month's holder of a number in: a driver signs in with his civil ID and his
    own password (the first time with the office's initial password), and the phone is contact data the office keeps."""

    phone_codes: bool = True


class MaintenanceSettings(_Section):
    approval_limit: Decimal = Field(Decimal("100.000"), ge=0, max_digits=12, decimal_places=3)  # quotes above it
    close_requires_invoice: bool = True  # a picked-up request closes once its invoice is approved


class AccidentsSettings(_Section):
    min_photos: int = Field(3, ge=1, le=12)  # camera photos a driver must take (several angles)
    police_report_alert_days: int = Field(2, ge=1, le=60)  # alert when an accident still has no police report


class PayrollSettings(_Section):
    # the share of a month's salary payroll may deduct; the rest moves to the next month (FR-PAY-03). Set by the client
    # after legal advice (BR-16): no default, and payroll will not run without it
    max_deduction_percent: Decimal | None = Field(None, gt=0, le=100, max_digits=5, decimal_places=2)
    # what the share is taken of: the basic salary, or the salary earned that month (after days the platform did
    # not count). Also the client's decision (BR-16)
    deduction_cap_base: Literal["basic", "gross"] = "gross"


class DailyReportSettings(_Section):
    require_orders_count: bool = True
    require_cash: bool = True
    require_screenshot: bool = True


class BrandingSettings(_Section):
    display_name: str = Field("BrilliantTech Fleet", min_length=2, max_length=60)
    primary_color: str = Field("#0A6CFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_file: str | None = Field(None, max_length=64)


class BrandingOut(BaseModel):
    display_name: str
    primary_color: str


SECTIONS: dict[str, type[_Section]] = {
    "tracking": TrackingSettings,
    "cash": CashSettings,
    "odometer": OdometerSettings,
    "documents": DocumentSettings,
    "onboarding": OnboardingSettings,
    "messaging": MessagingSettings,
    "driver_sign_in": DriverSignInSettings,
    "maintenance": MaintenanceSettings,
    "accidents": AccidentsSettings,
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


# ---- companies (legal entities) & branches (operational locations)


class CompanyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LocalizedText
    trade_name: LocalizedText | None = None
    cr_number: str | None = Field(default=None, max_length=30)
    license_number: str | None = Field(default=None, max_length=30)
    license_expiry: date | None = None
    pam_file_number: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=300)
    contact_name: str | None = Field(default=None, max_length=150)
    contact_phone: str | None = Field(default=None, max_length=20)


class CompanyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name: LocalizedText | None = None
    trade_name: LocalizedText | None = None
    cr_number: str | None = Field(default=None, max_length=30)
    license_number: str | None = Field(default=None, max_length=30)
    license_expiry: date | None = None
    pam_file_number: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=300)
    contact_name: str | None = Field(default=None, max_length=150)
    contact_phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class CompanyOut(BaseModel):
    id: int
    public_id: str
    name: dict[str, str]
    trade_name: dict[str, str] | None
    cr_number: str | None
    license_number: str | None
    license_expiry: date | None
    pam_file_number: str | None
    phone: str | None
    address: str | None
    contact_name: str | None
    contact_phone: str | None
    is_active: bool
    version: int


class CompanyOption(BaseModel):
    id: int
    public_id: str
    name: dict[str, str]
    is_active: bool


class BranchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LocalizedText


class BranchUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name: LocalizedText | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class BranchOut(BaseModel):
    id: int
    public_id: str
    name: dict[str, str]
    is_default: bool
    is_active: bool
    version: int
