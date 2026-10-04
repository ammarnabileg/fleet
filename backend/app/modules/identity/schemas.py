from pydantic import BaseModel, ConfigDict, Field

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
