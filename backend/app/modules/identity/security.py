from datetime import datetime

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id
_DUMMY_HASH = _hasher.hash("not-a-real-password-used-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Always does the same work, so a missing user cannot be told apart by timing."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def match_totp(secret: str, code: str, now: datetime, last_step: int | None) -> int | None:
    """Returns the matched time step (one step of clock drift allowed), or None.
    A step at or before `last_step` was already used and is rejected."""
    totp = pyotp.TOTP(secret)
    code = code.strip()
    current = totp.timecode(now)
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if totp.generate_otp(step) == code:
            return step
    return None
