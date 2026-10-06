"""Driver devices: phone + OTP binds one device to one driver; the app then uses rotating bearer tokens.

- OTP sent over WhatsApp (app.core.messaging): 6 digits, 5 minutes, 3 attempts, at most 3 requests per phone per
  15 minutes and 10 a day. The answer to a request is the same whether or not the phone belongs to a driver (or the
  message could be delivered): the endpoint cannot discover drivers.
- Or the supervisor sends a one-time activation link to the driver's registered WhatsApp number (24 hours): opening
  it binds the phone without an OTP.
- Binding a new device revokes the previous one (one active device per driver) and alerts the supervisors.
- Tokens are random strings stored only as hashes: access 15 minutes, refresh 30 days, rotated on every use. A
  refresh token used twice revokes its whole family (stolen token), except an immediate retry of the last rotation
  (the app lost the response on a bad network).
- Every request re-checks the driver: resignation, end of service or suspension stop the app at once.
Other modules use these through identity.service.
"""

import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import crypto, messaging
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity.models import ActivationLink, Device, DeviceStatus, DeviceToken, OtpChallenge
from app.modules.integrations import service as integrations
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 3
OTP_WINDOW = timedelta(minutes=15)
OTP_PER_WINDOW = 3
OTP_PER_DAY = 10  # with 3 attempts each: at most 30 guesses a day at a 6-digit code
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
RETRY_GRACE = timedelta(seconds=60)
ACTIVATION_TTL = timedelta(hours=24)
ACTIVATION_PER_DAY = 5
TOUCH_EVERY = timedelta(seconds=60)
log = logging.getLogger("fleet.devices")


@dataclass(frozen=True)
class DevicePrincipal:
    device_id: int
    employee_id: int
    employee_public_id: str
    company_id: int
    name: dict


def _otp_hash(phone: str, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"otp:{phone}:{code}".encode(), "sha256").hexdigest()


# ------------------------------------------------------------------ OTP


def _phone_sign_in(db: Session) -> None:
    """Without phone codes a number may be next month's SIM of another driver: a code to it would let him in."""
    if not org.phone_codes(db):
        raise AppError(403, "phone_sign_in_off")


def request_otp(db: Session, *, phone: str, device_uid: str, ip: str | None) -> None:
    _phone_sign_in(db)
    now = utcnow()

    def requests_since(t: datetime) -> int:
        return db.scalar(
            select(func.count())
            .select_from(OtpChallenge)
            .where(OtpChallenge.phone == phone, OtpChallenge.created_at > t)
        )

    # counted for unknown phones too: the limit reveals nothing
    if requests_since(now - OTP_WINDOW) >= OTP_PER_WINDOW or requests_since(now - timedelta(days=1)) >= OTP_PER_DAY:
        raise AppError(429, "otp_rate_limited", minutes=int(OTP_WINDOW.total_seconds() // 60))
    driver = people.driver_by_phone(db, phone)
    eligible = driver is not None and driver.can_use_app
    code = f"{secrets.randbelow(1_000_000):06d}" if eligible else None
    db.add(
        OtpChallenge(
            phone=phone,
            employee_id=driver.id if driver else None,
            device_uid=device_uid,
            code_hash=_otp_hash(phone, code) if code else None,
            expires_at=now + OTP_TTL,
            ip=ip,
        )
    )
    db.commit()
    if code:
        text = i18n.for_drivers(db, "messages.otp", code=code, minutes=OTP_TTL.seconds // 60)
        try:
            integrations.messenger(db).send(phone, text)
        except messaging.DeliveryError as exc:  # same answer to the phone; the supervisors are told instead
            log.warning("sign-in code not delivered: %s", exc)
            notifications.raise_alert(
                db,
                "otp_delivery_failed",
                company_id=driver.company_id,
                entity_type="employee",
                entity_id=driver.public_id,
                params={"driver": driver.name},
                dedupe_key=f"otp_delivery_failed:{driver.id}",
            )
            db.commit()


def _issue_tokens(db: Session, device_id: int, family: uuid.UUID) -> dict:
    now = utcnow()
    access, refresh = crypto.new_token(), crypto.new_token()
    db.add_all(
        [
            DeviceToken(
                device_id=device_id,
                token_hash=crypto.token_hash(access),
                kind="access",
                family=family,
                expires_at=now + ACCESS_TTL,
            ),
            DeviceToken(
                device_id=device_id,
                token_hash=crypto.token_hash(refresh),
                kind="refresh",
                family=family,
                expires_at=now + REFRESH_TTL,
            ),
        ]
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": int(ACCESS_TTL.total_seconds()),
    }


def _revoke_tokens(db: Session, *, device_id: int | None = None, family: uuid.UUID | None = None) -> None:
    q = update(DeviceToken).where(DeviceToken.revoked_at.is_(None))
    q = q.where(DeviceToken.device_id == device_id) if device_id is not None else q.where(DeviceToken.family == family)
    db.execute(q.values(revoked_at=func.now()))


def _revoke_device(db: Session, device: Device, reason: str) -> None:
    device.revoked_at, device.revoked_reason = utcnow(), reason
    _revoke_tokens(db, device_id=device.id)


def verify_otp(
    db: Session,
    *,
    phone: str,
    device_uid: str,
    code: str,
    platform: str | None,
    model: str | None,
    app_version: str | None,
) -> dict:
    _phone_sign_in(db)
    now = utcnow()
    challenge = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone, OtpChallenge.device_uid == device_uid, OtpChallenge.consumed_at.is_(None))
        .order_by(OtpChallenge.id.desc())
        .limit(1)
        .with_for_update()
    )
    if challenge is None or challenge.expires_at <= now:
        raise AppError(401, "otp_invalid")
    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        raise AppError(429, "otp_locked")
    challenge.attempts += 1
    if challenge.code_hash is None or not crypto.same(challenge.code_hash, _otp_hash(phone, code.strip())):
        db.commit()  # the attempt counts even though the request fails
        raise AppError(
            429 if challenge.attempts >= OTP_MAX_ATTEMPTS else 401,
            "otp_locked" if challenge.attempts >= OTP_MAX_ATTEMPTS else "otp_invalid",
        )
    driver = people.ref(db, challenge.employee_id)
    if driver is None or not driver.can_use_app:  # access changed after the code was sent
        db.commit()
        raise AppError(401, "otp_invalid")
    challenge.consumed_at = now
    device, tokens = _bind_device(
        db, driver, device_uid=device_uid, platform=platform, model=model, app_version=app_version, via="otp"
    )
    db.commit()
    return tokens


def _bind_device(
    db: Session,
    driver: people.EmployeeRef,
    *,
    device_uid: str,
    platform: str | None,
    model: str | None,
    app_version: str | None,
    via: str,
) -> tuple[Device, dict]:
    """One active device per driver: the previous one is revoked in the same transaction."""
    previous = db.scalar(
        select(Device).where(Device.employee_id == driver.id, Device.revoked_at.is_(None)).with_for_update()
    )
    if previous is not None:
        _revoke_device(db, previous, "replaced")
        db.flush()
    device = Device(
        employee_id=driver.id,
        device_uid=device_uid,
        platform=platform,
        model=model,
        app_version=app_version,
        last_seen_at=utcnow(),
    )
    db.add(device)
    db.flush()
    tokens = _issue_tokens(db, device.id, uuid.uuid4())
    if previous is not None and previous.device_uid != device_uid:  # the same phone signing in again is normal
        notifications.raise_alert(
            db,
            "device_replaced",
            company_id=driver.company_id,
            entity_type="employee",
            entity_id=driver.public_id,
            params={"driver": driver.name, "model": model or "-"},
        )
    audit.record(
        db,
        action="device.bound",
        entity_type="device",
        entity_id=device.public_id,
        actor_type="device",
        company_id=driver.company_id,
        after={
            "employee_id": str(driver.public_id),
            "platform": platform,
            "model": model,
            "via": via,
            "replaced": str(previous.public_id) if previous else None,
        },
    )
    emit(
        db,
        "driver.device_bound",
        device.public_id,
        {
            "device_id": str(device.public_id),
            "employee_id": str(driver.public_id),
            "replaced_device_id": str(previous.public_id) if previous else None,
        },
    )
    return device, tokens | {"device_id": str(device.public_id)}


# ------------------------------------------------------------------ activation links


def _masked(phone: str) -> str:
    return phone[:4] + "•" * (len(phone) - 8) + phone[-4:]


def create_activation_link(
    db: Session, driver: people.EmployeeRef, *, channel: str, actor_user_id: int, onboarding: bool = False
) -> dict:
    """A one-time link that binds the driver's phone without an OTP (first registration, or a supervisor-led
    phone change). "whatsapp" sends it to the driver's registered number and never shows it to the sender;
    "manual" shows it (a QR code at the office when WhatsApp is not available)."""
    if not driver.is_driver:
        raise AppError(422, "not_a_driver")
    if not driver.can_use_app:
        raise AppError(422, "driver_app_not_active")
    if channel == "whatsapp" and not driver.phone:
        raise AppError(422, "driver_phone_required")
    now = utcnow()
    recent = db.scalar(
        select(func.count())
        .select_from(ActivationLink)
        .where(ActivationLink.employee_id == driver.id, ActivationLink.created_at > now - timedelta(days=1))
    )
    if recent >= ACTIVATION_PER_DAY:
        raise AppError(429, "activation_rate_limited", count=ACTIVATION_PER_DAY)
    db.execute(
        update(ActivationLink)
        .where(
            ActivationLink.employee_id == driver.id,
            ActivationLink.used_at.is_(None),
            ActivationLink.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    token = crypto.new_token(32)
    link = ActivationLink(
        employee_id=driver.id,
        token_hash=crypto.token_hash(token),
        channel=channel,
        created_by=actor_user_id,
        expires_at=now + ACTIVATION_TTL,
    )
    db.add(link)
    db.flush()
    # the token travels after "#": browsers and link-preview robots never send it to a server
    url = f"{get_settings().public_url.rstrip('/')}/activate#t={token}"
    if channel == "whatsapp":
        text = i18n.for_drivers(
            db,
            "messages.activation_onboarding" if onboarding else "messages.activation",
            name=driver.name,
            url=url,
            hours=int(ACTIVATION_TTL.total_seconds() // 3600),
        )
        try:
            integrations.messenger(db).send(driver.phone, text)
        except messaging.NotOnWhatsApp:
            db.rollback()
            raise AppError(422, "phone_not_on_whatsapp", phone=driver.phone) from None
        except messaging.DeliveryError as exc:
            db.rollback()
            log.warning("activation link not delivered: %s", exc)
            raise AppError(502, "message_not_delivered") from None
    audit.record(
        db,
        action="device.activation_link_created",
        entity_type="employee",
        entity_id=driver.public_id,
        actor_user_id=actor_user_id,
        company_id=driver.company_id,
        after={"channel": channel},
    )
    db.commit()
    return {
        "channel": channel,
        "expires_at": link.expires_at,
        "url": url if channel == "manual" else None,
        "sent_to": _masked(driver.phone) if channel == "whatsapp" else None,
        "onboarding": onboarding,
    }


def activate(
    db: Session, *, token: str, device_uid: str, platform: str | None, model: str | None, app_version: str | None
) -> dict:
    link = db.scalar(
        select(ActivationLink).where(ActivationLink.token_hash == crypto.token_hash(token.strip())).with_for_update()
    )
    if link is None or link.used_at or link.revoked_at or link.expires_at <= utcnow():
        raise AppError(401, "activation_link_invalid")
    driver = people.ref(db, link.employee_id)
    if driver is None or not driver.can_use_app:  # access changed after the link was sent
        raise AppError(401, "activation_link_invalid")
    device, tokens = _bind_device(
        db,
        driver,
        device_uid=device_uid,
        platform=platform,
        model=model,
        app_version=app_version,
        via="activation_link",
    )
    link.used_at, link.used_device_id = utcnow(), device.id
    db.commit()
    return tokens


# ------------------------------------------------------------------ tokens


def refresh_tokens(db: Session, refresh_token: str) -> dict:
    now = utcnow()
    row = db.execute(
        select(DeviceToken, Device)
        .join(Device, Device.id == DeviceToken.device_id)
        .where(DeviceToken.token_hash == crypto.token_hash(refresh_token), DeviceToken.kind == "refresh")
        .with_for_update(of=DeviceToken)
    ).first()
    if row is None:
        raise AppError(401, "device_not_authenticated")
    token, device = row
    if token.revoked_at is not None:
        # a retry is allowed only for a token that was rotated away and whose successor is still live; after a
        # logout or a theft revocation the successor is revoked (or there is none), so nothing comes back
        successor = db.scalar(
            select(DeviceToken)
            .where(DeviceToken.family == token.family, DeviceToken.kind == "refresh", DeviceToken.id > token.id)
            .order_by(DeviceToken.id.desc())
            .limit(1)
        )
        is_retry = (
            successor is not None
            and successor.revoked_at is None
            and now - token.revoked_at <= RETRY_GRACE
            and device.revoked_at is None
        )
        _revoke_tokens(db, family=token.family)
        if not is_retry:
            audit.record(
                db,
                action="device.token_reused",
                entity_type="device",
                entity_id=device.public_id,
                actor_type="device",
            )
            db.commit()
            raise AppError(401, "token_reused")
    elif token.expires_at <= now:
        raise AppError(401, "device_not_authenticated")
    driver = people.ref(db, device.employee_id)
    if device.revoked_at is not None or driver is None or not driver.can_use_app:
        db.commit()
        raise AppError(401, "device_not_authenticated")
    _revoke_tokens(db, family=token.family)
    tokens = _issue_tokens(db, device.id, token.family)
    db.commit()
    return tokens


def require_device(request: Request, db: Session = Depends(get_session)) -> DevicePrincipal:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise AppError(401, "device_not_authenticated")
    row = db.execute(
        select(DeviceToken, Device)
        .join(Device, Device.id == DeviceToken.device_id)
        .where(DeviceToken.token_hash == crypto.token_hash(value.strip()), DeviceToken.kind == "access")
    ).first()
    now = utcnow()
    if row is None or row[0].revoked_at is not None or row[0].expires_at <= now or row[1].revoked_at is not None:
        raise AppError(401, "device_not_authenticated")
    device = row[1]
    driver = people.ref(db, device.employee_id)
    if driver is None or not driver.can_use_app:
        raise AppError(403, "driver_access_disabled")
    if device.last_seen_at is None or now - device.last_seen_at > TOUCH_EVERY:
        db.execute(update(Device).where(Device.id == device.id).values(last_seen_at=func.now()))
        db.commit()
    return DevicePrincipal(device.id, driver.id, str(driver.public_id), driver.company_id, driver.name)


def logout_device(db: Session, principal: DevicePrincipal) -> None:
    _revoke_tokens(db, device_id=principal.device_id)
    db.commit()


# ------------------------------------------------------------------ administration


def _device_out(d: Device) -> dict:
    return {
        "id": str(d.public_id),
        "platform": d.platform,
        "model": d.model,
        "app_version": d.app_version,
        "bound_at": d.bound_at,
        "last_seen_at": d.last_seen_at,
        "revoked_at": d.revoked_at,
        "revoked_reason": d.revoked_reason,
    }


def list_devices(db: Session, employee: people.EmployeeRef) -> list[dict]:
    q = select(Device).where(Device.employee_id == employee.id).order_by(Device.id.desc())
    return [_device_out(d) for d in db.scalars(q)]


def revoke_device(db: Session, public_id, *, actor_user_id: int, all_companies: bool, company_ids) -> None:
    device = db.scalar(select(Device).where(Device.public_id == public_id).with_for_update())
    driver = people.ref(db, device.employee_id) if device else None
    if device is None or not (all_companies or driver.company_id in set(company_ids)):
        raise AppError(404, "device_not_found")
    if device.revoked_at is None:
        _revoke_device(db, device, "unbound")
        audit.record(
            db,
            action="device.unbound",
            entity_type="device",
            entity_id=device.public_id,
            actor_user_id=actor_user_id,
            company_id=driver.company_id,
        )
    db.commit()


def revoke_employee_devices(db: Session, employee_id: int, *, reason: str, actor_user_id: int | None) -> int:
    devices = list(
        db.scalars(
            select(Device).where(Device.employee_id == employee_id, Device.revoked_at.is_(None)).with_for_update()
        )
    )
    for device in devices:
        _revoke_device(db, device, reason)
        audit.record(
            db,
            action="device.revoked",
            entity_type="device",
            entity_id=device.public_id,
            actor_user_id=actor_user_id,
            after={"reason": reason},
        )
    db.commit()
    return len(devices)


# ------------------------------------------------------------------ device health (heartbeat)

STATUS_FIELDS = (
    "location_permission",
    "gps_enabled",
    "battery_optimization_ignored",
    "tracking_service_running",
    "battery_level",
    "queue_size",
    "last_upload_at",
    "app_version",
)


def record_device_status(db: Session, device_id: int, data: dict) -> None:
    """Adds the latest health report to the caller's transaction."""
    values = {f: data.get(f) for f in STATUS_FIELDS}
    stmt = insert(DeviceStatus).values(device_id=device_id, payload=data.get("extra") or {}, **values)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["device_id"],
            set_={**values, "payload": stmt.excluded.payload, "reported_at": func.now()},
        )
    )


def device_status(db: Session, device_id: int) -> dict | None:
    s = db.get(DeviceStatus, device_id)
    return None if s is None else {f: getattr(s, f) for f in STATUS_FIELDS} | {"reported_at": s.reported_at}


def last_seen(db: Session, employee_ids) -> dict[int, datetime]:
    ids = list(employee_ids)
    if not ids:
        return {}
    q = select(Device.employee_id, Device.last_seen_at).where(Device.employee_id.in_(ids), Device.revoked_at.is_(None))
    return {e: t for e, t in db.execute(q) if t}


# ------------------------------------------------------------------ messaging channel health


def check_messaging_channel(db: Session) -> str:
    """Every few minutes: a WhatsApp session that dropped (it needs its QR code scanned again) or an unreachable
    Evolution API stops every new phone binding, so it alerts at once and closes itself when the channel is back."""
    try:
        state = integrations.messenger(db).connection_state()
    except messaging.DeliveryError:
        state = "unreachable"
    if state == "open":
        notifications.resolve(db, "messaging_down")
    else:
        notifications.raise_alert(
            db, "messaging_down", company_id=None, params={"state": state}, dedupe_key="messaging_down"
        )
    db.commit()
    return state
