"""An office user who forgot the password (BRD FR-USR-03): a one-time code to the phone saved on the account, then a
new password with it. With two-step verification on, the authenticator's code is asked too: a code on WhatsApp alone
must not open an account that needs two.

The page answers the same whether the username exists, is active or has a phone, so it tells nobody which usernames
are real; the limits are counted for unknown usernames too. Every attempt counts, the code serves once, and the new
password signs the account out everywhere."""

import hmac
import logging
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto, messaging
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import security
from app.modules.identity.models import PasswordResetCode, User
from app.modules.identity.service import _check_password_policy, _revoke_all_sessions
from app.modules.integrations import service as integrations

RESET_TTL = timedelta(minutes=10)
RESET_MAX_ATTEMPTS = 3
RESET_WINDOW = timedelta(minutes=15)
RESET_PER_WINDOW = 3
RESET_PER_DAY = 10
log = logging.getLogger("fleet.recovery")


def _hash(username: str, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"password-reset:{username}:{code}".encode(), "sha256").hexdigest()


def _key(username: str) -> str:
    return username.strip().lower()


def request_code(db: Session, username: str, *, ip: str | None) -> None:
    name, now = _key(username), utcnow()

    def since(t) -> int:
        return db.scalar(
            select(func.count())
            .select_from(PasswordResetCode)
            .where(PasswordResetCode.username == name, PasswordResetCode.created_at > t)
        )

    if since(now - RESET_WINDOW) >= RESET_PER_WINDOW or since(now - timedelta(days=1)) >= RESET_PER_DAY:
        raise AppError(429, "otp_rate_limited", minutes=int(RESET_WINDOW.total_seconds() // 60))
    user = db.scalar(select(User).where(func.lower(User.username) == name))
    eligible = user is not None and user.is_active and bool(user.phone)
    code = f"{secrets.randbelow(1_000_000):06d}" if eligible else None
    db.add(
        PasswordResetCode(
            username=name,
            user_id=user.id if user else None,
            code_hash=_hash(name, code) if code else None,
            expires_at=now + RESET_TTL,
            ip=ip,
        )
    )
    audit.record(
        db,
        action="auth.password_reset_requested",
        entity_type="user",
        entity_id=user.public_id if user else None,
        after={"username": name[:100], "sent": code is not None},
    )
    db.commit()
    if code:
        lang = user.locale or i18n.default_language(db).code
        text = i18n.t(db, lang, "messages.password_reset", code=code, minutes=int(RESET_TTL.total_seconds() // 60))
        try:
            integrations.messenger(db).send(user.phone, text)
        except messaging.DeliveryError as exc:  # the same answer on the page: the user asks an administrator
            log.warning("password reset code not delivered: %s", exc)


def reset(db: Session, username: str, *, code: str, new_password: str, mfa_code: str | None) -> None:
    _check_password_policy(new_password)  # before the attempt counts: a short password costs no attempt
    name, now = _key(username), utcnow()
    row = db.scalar(
        select(PasswordResetCode)
        .where(PasswordResetCode.username == name, PasswordResetCode.consumed_at.is_(None))
        .order_by(PasswordResetCode.id.desc())
        .limit(1)
        .with_for_update()
    )
    if row is None or row.expires_at <= now:
        raise AppError(401, "otp_invalid")
    if row.attempts >= RESET_MAX_ATTEMPTS:
        raise AppError(429, "otp_locked")
    row.attempts += 1
    user = db.get(User, row.user_id) if row.user_id else None
    if (
        row.code_hash is None
        or user is None
        or not user.is_active
        or not crypto.same(row.code_hash, _hash(name, code.strip()))
    ):
        db.commit()  # the attempt counts even though the request fails
        locked = row.attempts >= RESET_MAX_ATTEMPTS
        raise AppError(429 if locked else 401, "otp_locked" if locked else "otp_invalid")
    step = None
    if user.totp_enabled:
        step = security.match_totp(
            crypto.decrypt(user.totp_secret_enc), (mfa_code or "").strip(), now, user.totp_last_step
        )
        if step is None:
            db.commit()
            locked = row.attempts >= RESET_MAX_ATTEMPTS
            raise AppError(429 if locked else 401, "otp_locked" if locked else "mfa_code_invalid")
    row.consumed_at = now
    if step is not None:
        user.totp_last_step = step
    user.password_hash, user.must_change_password = security.hash_password(new_password), False
    user.failed_logins, user.locked_until, user.updated_at = 0, None, now
    _revoke_all_sessions(db, user.id)
    audit.record(
        db, action="user.password_reset_by_code", entity_type="user", entity_id=user.public_id, actor_user_id=user.id
    )
    db.commit()
