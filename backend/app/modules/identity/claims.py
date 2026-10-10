"""Signing in once with the civil ID, for a driver the office has no phone for (an imported list of civil IDs).

1. The office sets an initial password for drivers without a bound phone (from the import, the employee's page, or a
   selection), valid a number of days and usable once. Only a hash is stored.
2. The driver enters his civil ID and that password. A wrong answer says the same whether the civil ID exists or not;
   five wrong passwords lock the claim for 30 minutes, and failed tries from one network address are capped.
3. With phone codes (driver_sign_in.phone_codes, on by default): he enters his phone, a WhatsApp code is sent to it,
   and only the verified phone becomes his sign-in phone. Without them (a client whose numbers change hands): he
   chooses his own password instead, and signs in with his civil ID and it from then on, on any phone; his phone stays
   what the office records. Either way this phone is bound like after an activation link, and the self-registration
   (documents, IBAN) and its review follow, so nothing reaches the official records before a reviewer approves it.

A shared initial password is weak by nature (everyone told it knows it, and colleagues know each other's civil IDs):
the WhatsApp code, the single use, the expiry, the lock, the review and the log are what keep a claim honest. Without
phone codes nothing proves the phone, so the single use, the expiry, the lock and the review carry it alone, and his
own password replaces the shared one at once. A forgotten password is the office's: a new initial password.
"""

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto, messaging
from app.core.clock import utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import security
from app.modules.identity.devices import OTP_MAX_ATTEMPTS, OTP_TTL, _bind_device, _masked, _otp_hash
from app.modules.identity.models import ClaimAttempt, Device, DriverClaim
from app.modules.integrations import service as integrations
from app.modules.org import service as org
from app.modules.people import service as people

MAX_FAILURES = 5
LOCK = timedelta(minutes=30)
IP_FAILURES_PER_HOUR = 20
SESSION_TTL = timedelta(minutes=15)
OTP_SENDS = 3


def _bound(db: Session, employee_id: int) -> bool:
    q = select(Device.id).where(Device.employee_id == employee_id, Device.revoked_at.is_(None))
    return db.scalar(q) is not None


def has_bound_device(db: Session, employee_id: int) -> bool:
    """He uses the app on a phone (by a code, a link or his password): an initial password must not reopen it."""
    return _bound(db, employee_id)


# ------------------------------------------------------------------ the office


def set_claims(db: Session, employees, *, password: str, days: int, actor_user_id: int) -> dict:
    """In the caller's transaction. Drivers whose service ended are skipped, and with phone codes those who already
    have a bound phone (they change phones by code). Without phone codes this is also how a forgotten password is
    reset: his own password stops working at once, and he chooses a new one with the initial password."""
    hashed = security.hash_password(password)  # once: the same password for the whole batch
    expires = utcnow() + timedelta(days=days)
    codes = org.phone_codes(db)
    done, skipped = 0, []
    for e in employees:
        reason = (
            "not_a_driver"
            if not e.is_driver
            else "employment_ended"
            if e.is_terminal
            else "driver_access_disabled"
            if e.app_access in ("suspended", "disabled")
            else "device_already_bound"
            if codes and _bound(db, e.id)
            else None
        )
        if reason:
            skipped.append({"employee": {"id": str(e.public_id), "name": e.name}, "code": reason})
            continue
        row = db.get(DriverClaim, e.id, with_for_update=True)
        if row is None:
            row = DriverClaim(employee_id=e.id, password_hash=hashed, expires_at=expires, created_by=actor_user_id)
            db.add(row)
        for k, v in {
            "password_hash": hashed,
            "expires_at": expires,
            "created_by": actor_user_id,
            "created_at": utcnow(),
            "failures": 0,
            "locked_until": None,
            "session_hash": None,
            "session_device_uid": None,
            "session_expires_at": None,
            "phone": None,
            "otp_hash": None,
            "otp_expires_at": None,
            "otp_sent": 0,
            "otp_attempts": 0,
            "used_at": None,
            "used_phone": None,
            "used_device_id": None,
            "own_password_hash": None,
            "own_password_set_at": None,
        }.items():
            setattr(row, k, v)
        audit.record(
            db,
            action="driver.claim_set",
            entity_type="employee",
            entity_id=e.public_id,
            actor_user_id=actor_user_id,
            company_id=e.company_id,
            after={"expires_at": expires},
        )
        done += 1
    db.flush()
    return {"set": done, "skipped": skipped, "expires_at": expires}


def status(db: Session, employee_id: int) -> dict | None:
    row = db.get(DriverClaim, employee_id)
    if row is None:
        return None
    now = utcnow()
    return {
        "open": row.used_at is None and row.expires_at > now,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "locked": bool(row.locked_until and row.locked_until > now),
        "failures": row.failures,
        "used_at": row.used_at,
        "used_phone": _masked(row.used_phone) if row.used_phone else None,
        "own_password_set_at": row.own_password_set_at,
    }


def revoke(db: Session, employee, *, actor_user_id: int) -> None:
    row = db.get(DriverClaim, employee.id, with_for_update=True)
    if row is None or row.used_at is not None:
        raise AppError(404, "claim_not_found")
    db.delete(row)
    audit.record(
        db,
        action="driver.claim_revoked",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
    )
    db.commit()


# ------------------------------------------------------------------ the driver


def _attempt(db: Session, ip: str | None, ok: bool) -> None:
    db.add(ClaimAttempt(ip=ip, ok=ok))


def start(
    db: Session,
    *,
    civil_id: str,
    password: str,
    device_uid: str,
    ip: str | None,
    platform: str | None = None,
    model: str | None = None,
    app_version: str | None = None,
) -> dict:
    """The initial password opens a short session for the next step ("phone", or "password" without phone codes).
    Without phone codes his own password signs him in at once ("done"): this phone is bound."""
    now = utcnow()
    failed = db.scalar(
        select(func.count())
        .select_from(ClaimAttempt)
        .where(ClaimAttempt.ip == ip, ClaimAttempt.ok.is_(False), ClaimAttempt.at > now - timedelta(hours=1))
    )
    if failed >= IP_FAILURES_PER_HOUR:
        raise AppError(429, "claim_rate_limited", minutes=60)
    codes = org.phone_codes(db)
    driver = people.find(db, civil_id=civil_id, phone=None)
    row = db.get(DriverClaim, driver.id, with_for_update=True) if driver else None
    initial = row.password_hash if row and row.used_at is None and row.expires_at > now else None
    own = row.own_password_hash if row and not codes else None  # with phone codes he signs in with his phone
    # both checked every time: the same work whatever exists
    initial_ok = security.verify_password(initial, password)
    own_ok = security.verify_password(own, password)

    def refuse():
        _attempt(db, ip, False)
        db.commit()
        raise AppError(401, "claim_invalid")

    if row is None or (initial is None and own is None):
        refuse()
    if row.locked_until and row.locked_until > now:
        refuse()
    if not (initial_ok or own_ok):
        row.failures += 1
        if row.failures >= MAX_FAILURES:
            row.locked_until, row.failures = now + LOCK, 0
        refuse()
    if not driver.is_driver or driver.is_terminal or driver.app_access in ("suspended", "disabled"):
        refuse()
    row.failures, row.locked_until = 0, None
    if not initial_ok:  # his own password
        _attempt(db, ip, True)
        device, tokens = _bind_device(
            db, driver, device_uid=device_uid, platform=platform, model=model, app_version=app_version, via="password"
        )
        db.commit()
        return {"next": "done", "name": driver.name, "tokens": tokens}
    token = crypto.new_token(32)
    row.session_hash, row.session_device_uid, row.session_expires_at = (
        crypto.token_hash(token),
        device_uid,
        now + SESSION_TTL,
    )
    row.phone = row.otp_hash = row.otp_expires_at = None
    row.otp_sent = row.otp_attempts = 0
    _attempt(db, ip, True)
    db.commit()
    return {
        "next": "phone" if codes else "password",
        "claim_token": token,
        "name": driver.name,
        "expires_in": int(SESSION_TTL.total_seconds()),
    }


def _session(db: Session, token: str, device_uid: str) -> DriverClaim:
    row = db.scalar(
        select(DriverClaim).where(DriverClaim.session_hash == crypto.token_hash(token.strip())).with_for_update()
    )
    if (
        row is None
        or row.used_at is not None
        or row.session_device_uid != device_uid
        or row.session_expires_at is None
        or row.session_expires_at <= utcnow()
    ):
        raise AppError(401, "claim_session_invalid")
    return row


def _step(db: Session, *, phone_codes: bool) -> None:
    """The step the app is on must be the one this client signs in with (the setting may change in between)."""
    if org.phone_codes(db) != phone_codes:
        raise AppError(409, "sign_in_method_changed")


def send_code(db: Session, *, token: str, device_uid: str, phone: str) -> dict:
    _step(db, phone_codes=True)
    row = _session(db, token, device_uid)
    owner = people.find(db, civil_id=None, phone=phone)
    if owner is not None and owner.id != row.employee_id:
        raise AppError(409, "phone_taken")
    if row.otp_sent >= OTP_SENDS:
        raise AppError(429, "otp_rate_limited", minutes=int(SESSION_TTL.total_seconds() // 60))
    code = f"{secrets.randbelow(1_000_000):06d}"
    row.phone, row.otp_hash, row.otp_expires_at = phone, _otp_hash(phone, code), utcnow() + OTP_TTL
    row.otp_sent += 1
    row.otp_attempts = 0
    db.commit()
    text = i18n.for_drivers(db, "messages.otp", code=code, minutes=OTP_TTL.seconds // 60)
    try:
        integrations.messenger(db).send(phone, text)
    except messaging.NotOnWhatsApp:
        raise AppError(422, "phone_not_on_whatsapp", phone=phone) from None
    except messaging.DeliveryError:
        raise AppError(502, "message_not_delivered") from None
    return {"sent_to": _masked(phone), "expires_in": int(OTP_TTL.total_seconds())}


def verify(
    db: Session,
    *,
    token: str,
    device_uid: str,
    code: str,
    platform: str | None,
    model: str | None,
    app_version: str | None,
    on_claimed,
) -> dict:
    """on_claimed(driver): what follows a claim in the same transaction (the self-registration opens)."""
    _step(db, phone_codes=True)
    row = _session(db, token, device_uid)
    if row.otp_hash is None or row.otp_expires_at is None or row.otp_expires_at <= utcnow():
        raise AppError(401, "otp_invalid")
    if row.otp_attempts >= OTP_MAX_ATTEMPTS:
        raise AppError(429, "otp_locked")
    row.otp_attempts += 1
    if not crypto.same(row.otp_hash, _otp_hash(row.phone, code.strip())):
        db.commit()
        locked = row.otp_attempts >= OTP_MAX_ATTEMPTS
        raise AppError(429 if locked else 401, "otp_locked" if locked else "otp_invalid")
    return _claimed(
        db, row, phone=row.phone, device_uid=device_uid, meta=(platform, model, app_version), on_claimed=on_claimed
    )


def choose_password(
    db: Session,
    *,
    token: str,
    device_uid: str,
    password: str,
    platform: str | None,
    model: str | None,
    app_version: str | None,
    on_claimed,
) -> dict:
    """Without phone codes: the password he will sign in with from now on, in place of the shared initial one."""
    _step(db, phone_codes=False)
    row = _session(db, token, device_uid)
    driver = people.ref(db, row.employee_id)
    if password == driver.civil_id or security.verify_password(row.password_hash, password):
        raise AppError(422, "password_not_allowed")
    row.own_password_hash, row.own_password_set_at = security.hash_password(password), utcnow()
    return _claimed(
        db, row, phone=None, device_uid=device_uid, meta=(platform, model, app_version), on_claimed=on_claimed
    )


def _claimed(db: Session, row: DriverClaim, *, phone: str | None, device_uid: str, meta: tuple, on_claimed) -> dict:
    people.claim_app(db, row.employee_id, phone=phone)
    driver = people.ref(db, row.employee_id)
    on_claimed(driver)
    platform, model, app_version = meta
    device, tokens = _bind_device(
        db, driver, device_uid=device_uid, platform=platform, model=model, app_version=app_version, via="civil_id"
    )
    row.used_at, row.used_phone, row.used_device_id = utcnow(), phone, device.id
    row.session_hash = row.otp_hash = None
    audit.record(
        db,
        action="driver.claimed",
        entity_type="employee",
        entity_id=driver.public_id,
        actor_type="device",
        company_id=driver.company_id,
        after={"phone": phone, "own_password": phone is None, "device_id": str(device.public_id)},
    )
    db.commit()
    return tokens
