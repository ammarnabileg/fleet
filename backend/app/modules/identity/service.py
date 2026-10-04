"""Identity: authentication, sessions, authorization, user/role administration and driver devices.
Other modules use `Principal`, `get_principal`, `require_permission` and, for the driver app, `require_device`."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import crypto, permissions
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import security
from app.modules.identity.devices import (  # noqa: F401  (driver devices, used by other modules from here)
    DevicePrincipal,
    activate,
    check_messaging_channel,
    create_activation_link,
    device_status,
    list_devices,
    logout_device,
    record_device_status,
    refresh_tokens,
    request_otp,
    require_device,
    revoke_device,
    revoke_employee_devices,
    verify_otp,
)
from app.modules.identity.models import Role, RolePermission, User, UserCompany, UserRole
from app.modules.identity.models import Session as UserSession
from app.modules.org import service as org

SESSION_COOKIE = "fleet_session"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MFA_WINDOW = timedelta(minutes=5)
TOUCH_EVERY = timedelta(seconds=60)
ALL_PERMISSIONS = frozenset(permissions.CATALOG)


def utcnow() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ principal & dependencies


@dataclass(frozen=True)
class Principal:
    user_id: int
    public_id: str
    username: str
    full_name: str
    locale: str | None
    is_superuser: bool
    all_companies: bool
    permissions: frozenset[str]
    company_ids: frozenset[int]
    session_id: int
    csrf_token: str
    must_change_password: bool

    @property
    def sees_all_companies(self) -> bool:
        return self.is_superuser or self.all_companies

    def has(self, permission: str) -> bool:
        return self.is_superuser or permission in self.permissions

    def can_access_company(self, company_id: int) -> bool:
        return self.sees_all_companies or company_id in self.company_ids

    @property
    def scope(self) -> dict:
        """Keyword arguments for the scoped queries of other modules."""
        return {"all_companies": self.sees_all_companies, "company_ids": self.company_ids}


def _load_session(db: Session, token: str | None) -> tuple[UserSession, User] | None:
    if not token:
        return None
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == crypto.token_hash(token))
    ).first()
    if row is None:
        return None
    sess, user = row
    settings, now = get_settings(), utcnow()
    expired = (
        sess.revoked_at is not None
        or not user.is_active
        or now - sess.last_seen_at > timedelta(minutes=settings.session_idle_minutes)
        or now - sess.created_at > timedelta(hours=settings.session_absolute_hours)
        or (not sess.mfa_passed and now - sess.created_at > MFA_WINDOW)
    )
    return None if expired else (sess, user)


def _roles_permissions(db: Session, role_ids: Iterable[int]) -> frozenset[str]:
    role_ids = list(role_ids)
    if not role_ids:
        return frozenset()
    if db.scalar(select(func.count()).select_from(Role).where(Role.id.in_(role_ids), Role.all_permissions)):
        return ALL_PERMISSIONS
    perms = db.scalars(select(RolePermission.permission).where(RolePermission.role_id.in_(role_ids)))
    return frozenset(perms) & ALL_PERMISSIONS


def user_permissions(db: Session, user_id: int) -> frozenset[str]:
    return _roles_permissions(db, db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id)))


def user_company_ids(db: Session, user_id: int) -> frozenset[int]:
    return frozenset(db.scalars(select(UserCompany.company_id).where(UserCompany.user_id == user_id)))


def get_principal(request: Request, db: Session = Depends(get_session)) -> Principal:
    loaded = _load_session(db, request.cookies.get(SESSION_COOKIE))
    if loaded is None or not loaded[0].mfa_passed:
        raise AppError(401, "not_authenticated")
    sess, user = loaded
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER) or ""
        if not crypto.same(sent, sess.csrf_token):
            raise AppError(403, "csrf_failed")
    if utcnow() - sess.last_seen_at > TOUCH_EVERY:
        db.execute(update(UserSession).where(UserSession.id == sess.id).values(last_seen_at=func.now()))
        db.commit()
    return Principal(
        user_id=user.id,
        public_id=str(user.public_id),
        username=user.username,
        full_name=user.full_name,
        locale=user.locale,
        is_superuser=user.is_superuser,
        all_companies=user.all_companies,
        permissions=ALL_PERMISSIONS if user.is_superuser else user_permissions(db, user.id),
        company_ids=user_company_ids(db, user.id),
        session_id=sess.id,
        csrf_token=sess.csrf_token,
        must_change_password=user.must_change_password,
    )


def require_permission(permission: str):
    if not permissions.exists(permission):
        raise ValueError(f"unknown permission {permission!r}: add it to app/core/permissions.py")

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise AppError(403, "permission_denied", permission=permission)
        return principal

    return dependency


def permission_groups(db: Session, lang: str) -> list[dict]:
    """The catalog grouped by module with labels in `lang`, for the roles screen."""
    catalog = i18n.effective_catalog(db, lang)
    labels, modules = catalog.get("permissions", {}), catalog.get("modules", {})
    return [
        {
            "module": module,
            "label": modules.get(module, module),
            "permissions": [
                {"code": p.code, "action": p.action, "label": labels.get(p.code, p.code), "sensitive": p.sensitive}
                for p in perms
            ],
        }
        for module, perms in permissions.MODULES
    ]


# ------------------------------------------------------------------ authentication


@dataclass(frozen=True)
class LoginResult:
    token: str
    csrf_token: str
    mfa_required: bool


def _new_session(db: Session, user: User, *, mfa_passed: bool, ip: str | None, user_agent: str | None) -> LoginResult:
    token, csrf = crypto.new_token(), crypto.new_token(24)
    db.add(
        UserSession(
            token_hash=crypto.token_hash(token),
            user_id=user.id,
            mfa_passed=mfa_passed,
            csrf_token=csrf,
            ip=ip,
            user_agent=(user_agent or "")[:300],
        )
    )
    return LoginResult(token=token, csrf_token=csrf, mfa_required=not mfa_passed)


def _register_failure(db: Session, user: User, action: str) -> None:
    settings = get_settings()
    user.failed_logins += 1
    audit.record(db, action=action, entity_type="user", entity_id=user.public_id, actor_user_id=user.id)
    if user.failed_logins >= settings.login_max_failures:
        user.failed_logins = 0
        user.locked_until = utcnow() + timedelta(minutes=settings.login_lock_minutes)
        audit.record(
            db,
            action="auth.locked",
            entity_type="user",
            entity_id=user.public_id,
            actor_user_id=user.id,
            after={"locked_until": user.locked_until},
        )


def login(db: Session, username: str, password: str, *, ip: str | None, user_agent: str | None) -> LoginResult:
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    password_ok = security.verify_password(user.password_hash if user else None, password)
    if user is None or not user.is_active:
        audit.record(db, action="auth.login_failed", entity_type="user", after={"username": username.strip()[:100]})
        db.commit()
        raise AppError(401, "invalid_credentials")
    if user.locked_until and user.locked_until > utcnow():
        raise AppError(423, "account_locked")
    if not password_ok:
        _register_failure(db, user, "auth.login_failed")
        db.commit()
        raise AppError(401, "invalid_credentials")
    user.failed_logins, user.locked_until = 0, None
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    result = _new_session(db, user, mfa_passed=not user.totp_enabled, ip=ip, user_agent=user_agent)
    if not result.mfa_required:
        user.last_login_at = utcnow()
    audit.record(
        db,
        action="auth.login" if not result.mfa_required else "auth.password_ok_mfa_pending",
        entity_type="user",
        entity_id=user.public_id,
        actor_user_id=user.id,
    )
    db.commit()
    return result


def verify_mfa(db: Session, token: str | None, code: str, *, ip: str | None, user_agent: str | None) -> LoginResult:
    loaded = _load_session(db, token)
    if loaded is None or loaded[0].mfa_passed:
        raise AppError(401, "not_authenticated")
    sess, user = loaded
    if user.locked_until and user.locked_until > utcnow():
        raise AppError(423, "account_locked")
    step = security.match_totp(crypto.decrypt(user.totp_secret_enc), code, utcnow(), user.totp_last_step)
    if step is None:
        _register_failure(db, user, "auth.mfa_failed")
        if user.locked_until:
            sess.revoked_at = utcnow()
        db.commit()
        raise AppError(401, "invalid_code")
    user.totp_last_step, user.failed_logins, user.last_login_at = step, 0, utcnow()
    sess.revoked_at = utcnow()  # a new session id after MFA: no session fixation
    result = _new_session(db, user, mfa_passed=True, ip=ip, user_agent=user_agent)
    audit.record(db, action="auth.login", entity_type="user", entity_id=user.public_id, actor_user_id=user.id)
    db.commit()
    return result


def logout(db: Session, principal: Principal) -> None:
    db.execute(update(UserSession).where(UserSession.id == principal.session_id).values(revoked_at=func.now()))
    audit.record(
        db, action="auth.logout", entity_type="user", entity_id=principal.public_id, actor_user_id=principal.user_id
    )
    db.commit()


def _revoke_all_sessions(db: Session, user_id: int, except_session: int | None = None) -> None:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session:
        q = q.where(UserSession.id != except_session)
    db.execute(q.values(revoked_at=func.now()))


def _check_password_policy(password: str) -> None:
    minimum = get_settings().password_min_length
    if len(password) < minimum:
        raise AppError(422, "password_too_short", min=minimum)


def change_own_password(db: Session, principal: Principal, current: str, new: str) -> None:
    user = db.get(User, principal.user_id)
    if not security.verify_password(user.password_hash, current):
        raise AppError(403, "invalid_credentials")
    _check_password_policy(new)
    user.password_hash, user.must_change_password, user.updated_at = security.hash_password(new), False, utcnow()
    _revoke_all_sessions(db, user.id, except_session=principal.session_id)
    audit.record(
        db, action="user.password_changed", entity_type="user", entity_id=user.public_id, actor_user_id=user.id
    )
    db.commit()


def set_own_locale(db: Session, principal: Principal, locale: str | None) -> None:
    if locale is not None:
        i18n.get_language(db, locale)
    user = db.get(User, principal.user_id)
    user.locale = locale
    db.commit()


def start_totp_setup(db: Session, principal: Principal) -> str:
    user = db.get(User, principal.user_id)
    if user.totp_enabled:
        raise AppError(409, "mfa_already_enabled")
    secret = security.new_totp_secret()
    user.totp_secret_enc = crypto.encrypt(secret)
    db.commit()
    return security.totp_uri(secret, user.username, org.get_section(db, "branding").display_name)


def confirm_totp_setup(db: Session, principal: Principal, code: str) -> None:
    user = db.get(User, principal.user_id)
    if user.totp_enabled or not user.totp_secret_enc:
        raise AppError(409, "mfa_setup_not_started")
    step = security.match_totp(crypto.decrypt(user.totp_secret_enc), code, utcnow(), None)
    if step is None:
        raise AppError(422, "invalid_code")
    user.totp_enabled, user.totp_last_step = True, step
    _revoke_all_sessions(db, user.id, except_session=principal.session_id)
    audit.record(db, action="user.mfa_enabled", entity_type="user", entity_id=user.public_id, actor_user_id=user.id)
    db.commit()


# ------------------------------------------------------------------ users


def _user_snapshot(db: Session, user: User) -> dict:
    roles = db.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
        .order_by(Role.code)
    )
    return {
        "public_id": str(user.public_id),
        "username": user.username,
        "full_name": user.full_name,
        "phone": user.phone,
        "locale": user.locale,
        "is_active": user.is_active,
        "all_companies": user.all_companies,
        "is_superuser": user.is_superuser,
        "mfa_enabled": user.totp_enabled,
        "must_change_password": user.must_change_password,
        "version": user.version,
        "roles": list(roles),
        "company_ids": sorted(user_company_ids(db, user.id)),
    }


def _visible(principal: Principal, company_ids: frozenset[int], all_companies: bool) -> bool:
    """A company-limited administrator only sees users whose companies are all inside their own scope."""
    if principal.sees_all_companies:
        return True
    return not all_companies and bool(company_ids) and company_ids <= principal.company_ids


def _roles_by_code(db: Session, codes: Iterable[str]) -> list[Role]:
    codes = sorted(set(codes))
    roles = list(db.scalars(select(Role).where(Role.code.in_(codes))))
    missing = set(codes) - {r.code for r in roles}
    if missing:
        raise AppError(422, "unknown_role", codes=", ".join(sorted(missing)))
    return roles


def _guard_grants(db: Session, principal: Principal, roles: list[Role], all_companies: bool, company_ids: set[int]):
    """Nobody can hand out more than they hold: permissions, all-company access or companies outside their scope."""
    if not principal.is_superuser:
        if not _roles_permissions(db, [r.id for r in roles]) <= principal.permissions:
            raise AppError(403, "cannot_grant_permissions")
        if all_companies and not principal.all_companies:
            raise AppError(403, "company_out_of_scope")
        if not principal.all_companies and not company_ids <= principal.company_ids:
            raise AppError(403, "company_out_of_scope")
    if company_ids and not org.company_ids_exist(db, company_ids):
        raise AppError(422, "unknown_company")


def _set_links(db: Session, user_id: int, roles: list[Role], company_ids: set[int]) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    db.execute(delete(UserCompany).where(UserCompany.user_id == user_id))
    db.add_all([UserRole(user_id=user_id, role_id=r.id) for r in roles])
    db.add_all([UserCompany(user_id=user_id, company_id=c) for c in sorted(company_ids)])


def list_users(db: Session, principal: Principal) -> list[dict]:
    out = []
    for user in db.scalars(select(User).order_by(User.username)):
        if _visible(principal, user_company_ids(db, user.id), user.all_companies or user.is_superuser):
            out.append(_user_snapshot(db, user))
    return out


def _get_visible_user(db: Session, principal: Principal, public_id) -> User:
    user = db.scalar(select(User).where(User.public_id == public_id))
    if user is None or not _visible(principal, user_company_ids(db, user.id), user.all_companies or user.is_superuser):
        raise AppError(404, "user_not_found")
    return user


def create_user(
    db: Session,
    principal: Principal,
    *,
    username: str,
    full_name: str,
    phone: str | None,
    locale: str | None,
    password: str,
    role_codes: list[str],
    all_companies: bool,
    company_ids: list[int],
) -> dict:
    if db.scalar(select(User.id).where(func.lower(User.username) == username.strip().lower())):
        raise AppError(409, "username_taken")
    _check_password_policy(password)
    if locale is not None:
        i18n.get_language(db, locale)
    roles = _roles_by_code(db, role_codes)
    company_ids = set() if all_companies else set(company_ids)
    _guard_grants(db, principal, roles, all_companies, company_ids)
    user = User(
        username=username.strip(),
        full_name=full_name.strip(),
        phone=phone,
        locale=locale,
        password_hash=security.hash_password(password),
        must_change_password=True,
        all_companies=all_companies,
    )
    db.add(user)
    db.flush()
    _set_links(db, user.id, roles, company_ids)
    db.flush()
    snapshot = _user_snapshot(db, user)
    audit.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.public_id,
        actor_user_id=principal.user_id,
        after=snapshot,
    )
    db.commit()
    return snapshot


PORTAL_ROLE = "maintenance_center"


def _portal_role(db: Session) -> Role:
    """The role of maintenance-center accounts. Whoever manages centers may create these accounts without holding
    the portal permissions themselves (the generic rule for creating users), because the role grants nothing
    outside the portal and the portal shows only the center's own vehicles. If someone widened the role, this
    exception would hand out more than intended: refuse until the role is back to portal permissions only."""
    roles = _roles_by_code(db, [PORTAL_ROLE])
    perms = _roles_permissions(db, [roles[0].id])
    if roles[0].all_permissions or not perms or any(not p.startswith("portal.") for p in perms):
        raise AppError(409, "portal_role_changed", role=PORTAL_ROLE)
    return roles[0]


def create_portal_user(
    db: Session, *, actor_user_id: int, username: str, full_name: str, phone: str | None, password: str
) -> int:
    """A maintenance-center account: the portal role, no company scope (it sees no company data). In the caller's
    transaction; the caller links it to its center. Returns the user id."""
    if db.scalar(select(User.id).where(func.lower(User.username) == username.strip().lower())):
        raise AppError(409, "username_taken")
    _check_password_policy(password)
    role = _portal_role(db)
    user = User(
        username=username.strip(),
        full_name=full_name.strip(),
        phone=phone,
        password_hash=security.hash_password(password),
        must_change_password=True,
        all_companies=False,
    )
    db.add(user)
    db.flush()
    _set_links(db, user.id, [role], set())
    db.flush()
    audit.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.public_id,
        actor_user_id=actor_user_id,
        after=_user_snapshot(db, user),
    )
    return user.id


def set_portal_user_active(db: Session, user_id: int, *, active: bool, actor_user_id: int) -> None:
    """Disables or enables a maintenance-center account (its sessions end at once). In the caller's transaction."""
    user = db.get(User, user_id, with_for_update=True)
    if user is None or user.is_superuser:
        raise AppError(404, "user_not_found")
    if user.is_active == active:
        return
    before = _user_snapshot(db, user)
    user.is_active, user.version = active, user.version + 1
    user.updated_at = func.now()
    if not active:
        _revoke_all_sessions(db, user.id)
    db.flush()
    audit.record(
        db,
        action="user.updated",
        entity_type="user",
        entity_id=user.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after=_user_snapshot(db, user),
    )


def users_brief(db: Session, ids: Iterable[int]) -> list[dict]:
    """Accounts for another module's screens (a center's portal users)."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return []
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username))
    return [
        {
            "user_id": u.id,
            "public_id": str(u.public_id),
            "username": u.username,
            "full_name": u.full_name,
            "phone": u.phone,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at,
        }
        for u in users
    ]


def update_user(db: Session, principal: Principal, public_id, *, version: int, changes: dict) -> dict:
    user = _get_visible_user(db, principal, public_id)
    if user.version != version:
        raise AppError(409, "version_conflict")
    if user.is_superuser and not principal.is_superuser:
        raise AppError(403, "cannot_modify_superuser")
    if changes.get("locale") is not None:
        i18n.get_language(db, changes["locale"])
    before = _user_snapshot(db, user)
    for field in ("full_name", "phone", "locale", "is_active", "all_companies"):
        if field in changes:
            setattr(user, field, changes[field])
    if {"role_codes", "company_ids", "all_companies"} & changes.keys():
        roles = _roles_by_code(db, changes.get("role_codes", before["roles"]))
        company_ids = set() if user.all_companies else set(changes.get("company_ids", before["company_ids"]))
        _guard_grants(db, principal, roles, user.all_companies, company_ids)
        _set_links(db, user.id, roles, company_ids)
    if changes.get("is_active") is False:
        _revoke_all_sessions(db, user.id)
    user.version += 1
    user.updated_at = utcnow()
    db.flush()
    after = _user_snapshot(db, user)
    audit.record(
        db,
        action="user.updated",
        entity_type="user",
        entity_id=user.public_id,
        actor_user_id=principal.user_id,
        before=before,
        after=after,
    )
    db.commit()
    return after


def reset_password(db: Session, principal: Principal, public_id, new_password: str) -> None:
    user = _get_visible_user(db, principal, public_id)
    if user.is_superuser and not principal.is_superuser:
        raise AppError(403, "cannot_modify_superuser")
    _check_password_policy(new_password)
    user.password_hash, user.must_change_password = security.hash_password(new_password), True
    user.failed_logins, user.locked_until, user.updated_at = 0, None, utcnow()
    _revoke_all_sessions(db, user.id)
    audit.record(
        db, action="user.password_reset", entity_type="user", entity_id=user.public_id, actor_user_id=principal.user_id
    )
    db.commit()


# ------------------------------------------------------------------ roles


def _role_snapshot(db: Session, role: Role) -> dict:
    if role.all_permissions:
        perms = sorted(ALL_PERMISSIONS)
    else:
        perms = sorted(db.scalars(select(RolePermission.permission).where(RolePermission.role_id == role.id)))
    return {
        "code": role.code,
        "name": role.name,
        "is_system": role.is_system,
        "all_permissions": role.all_permissions,
        "permissions": perms,
        "version": role.version,
    }


def _check_permissions(principal: Principal, wanted: list[str]) -> set[str]:
    wanted = set(wanted)
    unknown = wanted - ALL_PERMISSIONS
    if unknown:
        raise AppError(422, "unknown_permission", codes=", ".join(sorted(unknown)))
    if not principal.is_superuser and not wanted <= principal.permissions:
        raise AppError(403, "cannot_grant_permissions")
    return wanted


def list_roles(db: Session) -> list[dict]:
    return [_role_snapshot(db, r) for r in db.scalars(select(Role).order_by(Role.code))]


def create_role(db: Session, principal: Principal, *, code: str, name: dict, permissions: list[str]) -> dict:
    wanted = _check_permissions(principal, permissions)
    name = i18n.validate_localized(db, name)
    if db.scalar(select(Role.id).where(Role.code == code)):
        raise AppError(409, "role_exists")
    role = Role(code=code, name=name, all_permissions=False)
    db.add(role)
    db.flush()
    db.add_all([RolePermission(role_id=role.id, permission=p) for p in sorted(wanted)])
    db.flush()
    snapshot = _role_snapshot(db, role)
    audit.record(
        db, action="role.created", entity_type="role", entity_id=code, actor_user_id=principal.user_id, after=snapshot
    )
    db.commit()
    return snapshot


def update_role(db: Session, principal: Principal, code: str, *, version: int, changes: dict) -> dict:
    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        raise AppError(404, "role_not_found")
    if role.is_system:
        raise AppError(403, "system_role")
    if role.version != version:
        raise AppError(409, "version_conflict")
    before = _role_snapshot(db, role)
    if "name" in changes:
        role.name = i18n.validate_localized(db, changes["name"])
    if "permissions" in changes:
        wanted = _check_permissions(principal, changes["permissions"])
        db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        db.add_all([RolePermission(role_id=role.id, permission=p) for p in sorted(wanted)])
    role.version += 1
    db.flush()
    after = _role_snapshot(db, role)
    audit.record(
        db,
        action="role.updated",
        entity_type="role",
        entity_id=code,
        actor_user_id=principal.user_id,
        before=before,
        after=after,
    )
    db.commit()
    return after


def user_names(db: Session, ids: Iterable[int]) -> dict[int, str]:
    """Display names for other modules (the audit log shows who acted)."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {
        i: f"{name} ({username})"
        for i, name, username in db.execute(select(User.id, User.full_name, User.username).where(User.id.in_(ids)))
    }


def bootstrap_superuser(db: Session, *, username: str, full_name: str, password: str) -> str:
    """First administrator of a new installation (ops command). Refuses if any superuser exists."""
    if db.scalar(select(User.id).where(User.is_superuser.is_(True))):
        raise AppError(409, "superuser_exists")
    _check_password_policy(password)
    user = User(
        username=username,
        full_name=full_name,
        password_hash=security.hash_password(password),
        is_superuser=True,
        all_companies=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=db.scalar(select(Role.id).where(Role.code == "system_admin"))))
    audit.record(
        db,
        action="user.bootstrapped",
        entity_type="user",
        entity_id=user.public_id,
        actor_type="system",
        after={"username": username},
    )
    db.commit()
    return str(user.public_id)
