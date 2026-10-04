from pydantic import BaseModel, ConfigDict, Field

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


class TotpSetupOut(BaseModel):
    otpauth_uri: str


class MeOut(BaseModel):
    public_id: str
    username: str
    full_name: str
    is_superuser: bool
    all_branches: bool
    permissions: list[str]
    branch_ids: list[int]
    csrf_token: str
    must_change_password: bool


class UserOut(BaseModel):
    public_id: str
    username: str
    full_name: str
    phone: str | None
    is_active: bool
    all_branches: bool
    is_superuser: bool
    mfa_enabled: bool
    must_change_password: bool
    version: int
    roles: list[str]
    branch_ids: list[int]


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(max_length=200)
    role_codes: list[str] = []
    all_branches: bool = False
    branch_ids: list[int] = []


class UserUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    all_branches: bool | None = None
    role_codes: list[str] | None = None
    branch_ids: list[int] | None = None


class RoleOut(BaseModel):
    code: str
    name_ar: str
    name_en: str
    is_system: bool
    permissions: list[str]
    version: int


class RoleCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=CODE)
    name_ar: str = Field(min_length=2, max_length=100)
    name_en: str = Field(min_length=2, max_length=100)
    permissions: list[str] = []


class RoleUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    name_ar: str | None = Field(default=None, min_length=2, max_length=100)
    name_en: str | None = Field(default=None, min_length=2, max_length=100)
    permissions: list[str] | None = None


class PermissionOut(BaseModel):
    code: str
    name_ar: str
    name_en: str
