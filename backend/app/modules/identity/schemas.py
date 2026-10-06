import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import LangCode, LocalizedText

CODE = r"^[a-z][a-z0-9_]{1,49}$"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    mfa_required: bool
    csrf_token: str | None = None


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=200)


class PasswordResetIn(BaseModel):
    new_password: str = Field(max_length=200)


class LocaleIn(BaseModel):
    locale: LangCode | None


class TotpSetupOut(BaseModel):
    otpauth_uri: str


class MeOut(BaseModel):
    public_id: str
    username: str
    full_name: str
    locale: str | None
    is_superuser: bool
    all_companies: bool
    permissions: list[str]
    company_ids: list[int]
    csrf_token: str
    must_change_password: bool


class UserOut(BaseModel):
    public_id: str
    username: str
    full_name: str
    phone: str | None
    locale: str | None
    is_active: bool
    all_companies: bool
    is_superuser: bool
    mfa_enabled: bool
    must_change_password: bool
    version: int
    roles: list[str]
    company_ids: list[int]


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    locale: LangCode | None = None
    password: str = Field(max_length=200)
    role_codes: list[str] = []
    all_companies: bool = True
    company_ids: list[int] = []


class UserUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    locale: LangCode | None = None
    is_active: bool | None = None
    all_companies: bool | None = None
    role_codes: list[str] | None = None
    company_ids: list[int] | None = None


class RoleOut(BaseModel):
    code: str
    name: dict[str, str]
    is_system: bool
    all_permissions: bool
    permissions: list[str]
    version: int


class RoleCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=CODE)
    name: LocalizedText
    permissions: list[str] = []


class RoleUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name: LocalizedText | None = None
    permissions: list[str] | None = None


class PermissionOut(BaseModel):
    code: str
    action: str
    label: str
    sensitive: bool


class PermissionGroupOut(BaseModel):
    module: str
    label: str
    permissions: list[PermissionOut]


# ---- driver devices

Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+[1-9][0-9]{7,14}$")]
DeviceUid = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=128)]
Meta = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: Phone
    device_uid: DeviceUid


class OtpVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: Phone
    device_uid: DeviceUid
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{6}$")]
    platform: Meta | None = None
    model: Meta | None = None
    app_version: Meta | None = None


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: Annotated[str, StringConstraints(min_length=20, max_length=200)]


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    device_id: str | None = None


class DeviceOut(BaseModel):
    id: str
    platform: str | None
    model: str | None
    app_version: str | None
    bound_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    revoked_reason: str | None


class ActivationLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["whatsapp", "manual"] = "whatsapp"
    # the driver completes his data, documents and vehicle in the app first; default: until he is registered
    onboarding: bool | None = None


class ActivationLinkOut(BaseModel):
    channel: str
    expires_at: datetime
    url: str | None  # only for "manual"; a WhatsApp link is never shown to the sender
    sent_to: str | None  # the registered number, masked
    onboarding: bool


class ActivateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=100)]
    device_uid: DeviceUid
    platform: Meta | None = None
    model: Meta | None = None
    app_version: Meta | None = None


class BulkLinksIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_ids: list[str] = Field(default_factory=list, max_length=1000)
    all_unbound: bool = False  # every driver with app access and no phone bound yet


class SkippedOut(BaseModel):
    id: str
    reason: str


class BulkLinksOut(BaseModel):
    queued: int
    skipped: list[SkippedOut]


class QueueItemOut(BaseModel):
    id: str
    driver: dict | None
    status: str
    onboarding: bool
    requested_at: datetime
    sent_at: datetime | None
    error: str | None
    attempts: int


class QueueOut(BaseModel):
    waiting: int
    sent_today: int
    daily_limit: int
    estimated_days: int
    items: list[QueueItemOut]


# ---- signing in once with the civil ID (drivers imported without a phone)

InitialPassword = Annotated[str, StringConstraints(min_length=8, max_length=64)]


class ClaimStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    civil_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{12}$")]
    password: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    device_uid: DeviceUid
    platform: Meta | None = None  # bound at once when it is his own password (no phone codes)
    model: Meta | None = None
    app_version: Meta | None = None


class ClaimStartOut(BaseModel):
    next: Literal["phone", "password", "done"]  # done: his own password, signed in (tokens)
    name: dict[str, str]  # "Welcome, ..." before he goes on
    claim_token: str | None = None
    expires_in: int | None = None
    tokens: TokensOut | None = None


class ClaimPhoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=100)]
    device_uid: DeviceUid
    phone: Phone


class ClaimPhoneOut(BaseModel):
    sent_to: str
    expires_in: int


class ClaimVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=100)]
    device_uid: DeviceUid
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{6}$")]
    platform: Meta | None = None
    model: Meta | None = None
    app_version: Meta | None = None


class ClaimPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=100)]
    device_uid: DeviceUid
    password: InitialPassword  # the same rule: 8 to 64 characters
    platform: Meta | None = None
    model: Meta | None = None
    app_version: Meta | None = None


class ClaimsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    password: InitialPassword
    days: int = Field(14, ge=1, le=60)


class ClaimSkipped(BaseModel):
    employee: dict
    code: str


class ClaimsOut(BaseModel):
    set: int
    skipped: list[ClaimSkipped]
    expires_at: datetime


class ClaimStatusOut(BaseModel):
    open: bool
    expires_at: datetime
    created_at: datetime
    locked: bool
    failures: int
    used_at: datetime | None
    used_phone: str | None
    own_password_set_at: datetime | None  # without phone codes: he chose his own password then
