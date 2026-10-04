"""Identity: authentication, sessions, authorization and user/role administration.
Other modules use only `Principal`, `get_principal` and `require_permission` from here."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.identity import security
from app.modules.identity.models import Role, RolePermission, User, UserBranch, UserRole
from app.modules.identity.models import Session as UserSession
from app.modules.identity.permissions import CATALOG
from app.modules.org import service as org

SESSION_COOKIE = "fleet_session"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MFA_WINDOW = timedelta(minutes=5)
TOUCH_EVERY = timedelta(seconds=60)


def utcnow() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ principal & dependencies


@dataclass(frozen=True)
class Principal:
    user_id: int
    public_id: str
    username: str
    full_name: str
    is_superuser: bool
    all_branches: bool
    permissions: frozenset[str]
    branch_ids: frozenset[int]
    session_id: int
    csrf_token: str
    must_change_password: bool

    @property
    def sees_all_branches(self) -> bool:
        return self.is_superuser or self.all_branches

    def has(self, permission: str) -> bool:
        return self.is_superuser or permission in self.permissions

    def can_access_branch(self, branch_id: int) -> bool:
        return self.sees_all_branches or branch_id in self.branch_ids


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


def user_permissions(db: Session, user_id: int) -> frozenset[str]:
    q = (
        select(RolePermission.permission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    return frozenset(db.scalars(q))


def user_branch_ids(db: Session, user_id: int) -> frozenset[int]:
    return frozenset(db.scalars(select(UserBranch.branch_id).where(UserBranch.user_id == user_id)))


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
        is_superuser=user.is_superuser,
        all_branches=user.all_branches,
        permissions=user_permissions(db, user.id),
        branch_ids=user_branch_ids(db, user.id),
        session_id=sess.id,
        csrf_token=sess.csrf_token,
        must_change_password=user.must_change_password,
    )


def require_permission(permission: str):
    if permission not in CATALOG:
        raise ValueError(f"unknown permission {permission!r}")

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise AppError(403, "permission_denied", permission)
        return principal

    return dependency


def catalog() -> dict[str, tuple[str, str]]:
    return dict(CATALOG)


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
    if len(password) < get_settings().password_min_length:
        raise AppError(422, "password_too_short", f"minimum {get_settings().password_min_length} characters")


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


# ------------------------------------------------------------------ administration


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
        "is_active": user.is_active,
        "all_branches": user.all_branches,
        "is_superuser": user.is_superuser,
        "mfa_enabled": user.totp_enabled,
        "must_change_password": user.must_change_password,
        "version": user.version,
        "roles": list(roles),
        "branch_ids": sorted(user_branch_ids(db, user.id)),
    }


def _visible(principal: Principal, branch_ids: frozenset[int], all_branches: bool) -> bool:
    if principal.sees_all_branches:
        return True
    return not all_branches and bool(branch_ids) and branch_ids <= principal.branch_ids


def _roles_by_code(db: Session, codes: Iterable[str]) -> list[Role]:
    codes = sorted(set(codes))
    roles = list(db.scalars(select(Role).where(Role.code.in_(codes))))
    missing = set(codes) - {r.code for r in roles}
    if missing:
        raise AppError(422, "unknown_role", ", ".join(sorted(missing)))
    return roles


def _role_permissions(db: Session, role_ids: Iterable[int]) -> set[str]:
    return set(db.scalars(select(RolePermission.permission).where(RolePermission.role_id.in_(list(role_ids)))))


def _guard_grants(db: Session, principal: Principal, roles: list[Role], all_branches: bool, branch_ids: set[int]):
    """Nobody can hand out more than they hold: permissions, all-branch access or branches outside their scope."""
    if principal.is_superuser:
        pass
    elif not _role_permissions(db, [r.id for r in roles]) <= principal.permissions:
        raise AppError(403, "cannot_grant_permissions")
    elif all_branches and not principal.all_branches:
        raise AppError(403, "branch_out_of_scope")
    elif not principal.all_branches and not branch_ids <= principal.branch_ids:
        raise AppError(403, "branch_out_of_scope")
    if branch_ids and not org.branch_ids_exist(db, branch_ids):
        raise AppError(422, "unknown_branch")


def _set_links(db: Session, user_id: int, roles: list[Role], branch_ids: set[int]) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    db.execute(delete(UserBranch).where(UserBranch.user_id == user_id))
    db.add_all([UserRole(user_id=user_id, role_id=r.id) for r in roles])
    db.add_all([UserBranch(user_id=user_id, branch_id=b) for b in sorted(branch_ids)])


def list_users(db: Session, principal: Principal) -> list[dict]:
    users = db.scalars(select(User).order_by(User.username))
    out = []
    for user in users:
        if _visible(principal, user_branch_ids(db, user.id), user.all_branches or user.is_superuser):
            out.append(_user_snapshot(db, user))
    return out


def _get_visible_user(db: Session, principal: Principal, public_id: str) -> User:
    user = db.scalar(select(User).where(User.public_id == public_id))
    if user is None or not _visible(principal, user_branch_ids(db, user.id), user.all_branches or user.is_superuser):
        raise AppError(404, "user_not_found")
    return user


def create_user(
    db: Session,
    principal: Principal,
    *,
    username: str,
    full_name: str,
    phone: str | None,
    password: str,
    role_codes: list[str],
    all_branches: bool,
    branch_ids: list[int],
) -> dict:
    if db.scalar(select(User.id).where(func.lower(User.username) == username.strip().lower())):
        raise AppError(409, "username_taken")
    _check_password_policy(password)
    roles = _roles_by_code(db, role_codes)
    _guard_grants(db, principal, roles, all_branches, set(branch_ids))
    user = User(
        username=username.strip(),
        full_name=full_name.strip(),
        phone=phone,
        password_hash=security.hash_password(password),
        must_change_password=True,
        all_branches=all_branches,
    )
    db.add(user)
    db.flush()
    _set_links(db, user.id, roles, set(branch_ids))
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


def update_user(db: Session, principal: Principal, public_id: str, *, version: int, changes: dict) -> dict:
    user = _get_visible_user(db, principal, public_id)
    if user.version != version:
        raise AppError(409, "version_conflict")
    if user.is_superuser and not principal.is_superuser:
        raise AppError(403, "cannot_modify_superuser")
    before = _user_snapshot(db, user)
    for field in ("full_name", "phone", "is_active", "all_branches"):
        if field in changes:
            setattr(user, field, changes[field])
    if {"role_codes", "branch_ids", "all_branches"} & changes.keys():
        roles = _roles_by_code(db, changes.get("role_codes", before["roles"]))
        branch_ids = set(changes.get("branch_ids", before["branch_ids"]))
        _guard_grants(db, principal, roles, user.all_branches, branch_ids)
        _set_links(db, user.id, roles, branch_ids)
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


def reset_password(db: Session, principal: Principal, public_id: str, new_password: str) -> None:
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


def _role_snapshot(db: Session, role: Role) -> dict:
    perms = sorted(db.scalars(select(RolePermission.permission).where(RolePermission.role_id == role.id)))
    return {
        "code": role.code,
        "name_ar": role.name_ar,
        "name_en": role.name_en,
        "is_system": role.is_system,
        "permissions": perms,
        "version": role.version,
    }


def _check_permissions(principal: Principal, permissions: list[str]) -> set[str]:
    wanted = set(permissions)
    unknown = wanted - CATALOG.keys()
    if unknown:
        raise AppError(422, "unknown_permission", ", ".join(sorted(unknown)))
    if not principal.is_superuser and not wanted <= principal.permissions:
        raise AppError(403, "cannot_grant_permissions")
    return wanted


def list_roles(db: Session) -> list[dict]:
    return [_role_snapshot(db, r) for r in db.scalars(select(Role).order_by(Role.code))]


def create_role(
    db: Session, principal: Principal, *, code: str, name_ar: str, name_en: str, permissions: list[str]
) -> dict:
    wanted = _check_permissions(principal, permissions)
    if db.scalar(select(Role.id).where(Role.code == code)):
        raise AppError(409, "role_exists")
    role = Role(code=code, name_ar=name_ar, name_en=name_en)
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
    for field in ("name_ar", "name_en"):
        if field in changes:
            setattr(role, field, changes[field])
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
        all_branches=True,
    )
    db.add(user)
    db.flush()
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
