import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = hashlib.sha256(b"fleet:field-encryption:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
