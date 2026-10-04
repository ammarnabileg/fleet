import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.modules.i18n import service as i18n
from app.modules.identity import schemas, service
from app.modules.identity.service import Principal, get_principal, require_permission
from app.modules.people import service as people

router = APIRouter(prefix="/api/v1", tags=["identity"])


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        service.SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_absolute_hours * 3600,
    )


def _client(request: Request) -> dict:
    return {"ip": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent")}


@router.post("/auth/login", response_model=schemas.LoginOut)
def login(body: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_session)):
    result = service.login(db, body.username, body.password, **_client(request))
    _set_cookie(response, result.token)
    return schemas.LoginOut(
        mfa_required=result.mfa_required, csrf_token=None if result.mfa_required else result.csrf_token
    )


@router.post("/auth/mfa/verify", response_model=schemas.LoginOut)
def verify_mfa(body: schemas.CodeIn, request: Request, response: Response, db: Session = Depends(get_session)):
    result = service.verify_mfa(db, request.cookies.get(service.SESSION_COOKIE), body.code, **_client(request))
    _set_cookie(response, result.token)
    return schemas.LoginOut(mfa_required=False, csrf_token=result.csrf_token)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    service.logout(db, principal)
    response.delete_cookie(service.SESSION_COOKIE, path="/")


@router.get("/auth/me", response_model=schemas.MeOut)
def me(principal: Principal = Depends(get_principal)):
    return schemas.MeOut(
        public_id=principal.public_id,
        username=principal.username,
        full_name=principal.full_name,
        locale=principal.locale,
        is_superuser=principal.is_superuser,
        all_companies=principal.all_companies,
        permissions=sorted(principal.permissions),
        company_ids=sorted(principal.company_ids),
        csrf_token=principal.csrf_token,
        must_change_password=principal.must_change_password,
    )


@router.put("/auth/me/locale", status_code=204)
def set_locale(
    body: schemas.LocaleIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)
):
    service.set_own_locale(db, principal, body.locale)


@router.post("/auth/password", status_code=204)
def change_password(
    body: schemas.PasswordChangeIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)
):
    service.change_own_password(db, principal, body.current_password, body.new_password)


@router.post("/auth/mfa/setup", response_model=schemas.TotpSetupOut)
def mfa_setup(principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return schemas.TotpSetupOut(otpauth_uri=service.start_totp_setup(db, principal))


@router.post("/auth/mfa/enable", status_code=204)
def mfa_enable(body: schemas.CodeIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    service.confirm_totp_setup(db, principal, body.code)


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(principal: Principal = Depends(require_permission("users.view")), db: Session = Depends(get_session)):
    return service.list_users(db, principal)


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    body: schemas.UserCreateIn,
    principal: Principal = Depends(require_permission("users.create")),
    db: Session = Depends(get_session),
):
    return service.create_user(db, principal, **body.model_dump())


@router.patch("/users/{public_id}", response_model=schemas.UserOut)
def update_user(
    public_id: uuid.UUID,
    body: schemas.UserUpdateIn,
    principal: Principal = Depends(require_permission("users.update")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_user(db, principal, public_id, version=version, changes=changes)


@router.post("/users/{public_id}/password", status_code=204)
def reset_password(
    public_id: uuid.UUID,
    body: schemas.PasswordResetIn,
    principal: Principal = Depends(require_permission("users.update")),
    db: Session = Depends(get_session),
):
    service.reset_password(db, principal, public_id, body.new_password)


@router.get("/roles", response_model=list[schemas.RoleOut])
def list_roles(_: Principal = Depends(require_permission("roles.view")), db: Session = Depends(get_session)):
    return service.list_roles(db)


@router.post("/roles", response_model=schemas.RoleOut, status_code=201)
def create_role(
    body: schemas.RoleCreateIn,
    principal: Principal = Depends(require_permission("roles.manage")),
    db: Session = Depends(get_session),
):
    return service.create_role(db, principal, **body.model_dump())


@router.patch("/roles/{code}", response_model=schemas.RoleOut)
def update_role(
    code: str,
    body: schemas.RoleUpdateIn,
    principal: Principal = Depends(require_permission("roles.manage")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_role(db, principal, code, version=version, changes=changes)


@router.get("/permissions", response_model=list[schemas.PermissionGroupOut])
def list_permissions(
    request: Request,
    lang: str | None = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_session),
):
    code = lang or i18n.negotiate(db, principal.locale, request.headers.get("accept-language"))
    return service.permission_groups(db, code)


# ---- driver app: binding by phone + OTP, then rotating bearer tokens (no cookies, so no CSRF)


@router.post("/driver/auth/otp", status_code=202)
def request_otp(body: schemas.OtpRequestIn, request: Request, db: Session = Depends(get_session)):
    """Same answer whether or not the phone belongs to a driver."""
    service.request_otp(db, phone=body.phone, device_uid=body.device_uid, ip=_client(request)["ip"])
    return {"status": "sent"}


@router.post("/driver/auth/verify", response_model=schemas.TokensOut)
def verify_otp(body: schemas.OtpVerifyIn, db: Session = Depends(get_session)):
    return service.verify_otp(
        db,
        phone=body.phone,
        device_uid=body.device_uid,
        code=body.code,
        platform=body.platform,
        model=body.model,
        app_version=body.app_version,
    )


@router.post("/driver/auth/refresh", response_model=schemas.TokensOut)
def refresh(body: schemas.RefreshIn, db: Session = Depends(get_session)):
    return service.refresh_tokens(db, body.refresh_token)


@router.post("/driver/auth/logout", status_code=204)
def driver_logout(
    device: service.DevicePrincipal = Depends(service.require_device), db: Session = Depends(get_session)
):
    service.logout_device(db, device)


# ---- driver devices administration


@router.get("/employees/{public_id}/devices", response_model=list[schemas.DeviceOut])
def list_devices(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("devices.manage")),
    db: Session = Depends(get_session),
):
    return service.list_devices(db, people.ref_by_public_id(db, public_id, **principal.scope))


@router.post("/devices/{public_id}/revoke", status_code=204)
def revoke_device(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("devices.manage")),
    db: Session = Depends(get_session),
):
    """Unbind: the driver must verify the phone again (OTP) to use the app."""
    service.revoke_device(db, public_id, actor_user_id=principal.user_id, **principal.scope)
