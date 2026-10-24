"""The secrets of a transfer file, sealed with a passphrase the user types: AES-256-GCM with a key derived by scrypt
from the passphrase and a random salt. The passphrase is never stored or sent back; without it the secrets cannot be
read (a wrong one fails the authentication tag, it never yields garbage)."""

import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.core.errors import AppError

ALG, KDF = "AES-256-GCM", "scrypt"
N, R, P = 2**15, 8, 1
AAD = b"fleet-config/secrets/v1"
MIN_PASSPHRASE = 10


def _key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode())


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def seal(values: dict, passphrase: str) -> dict:
    if len(passphrase or "") < MIN_PASSPHRASE:
        raise AppError(422, "config_passphrase_short", min=MIN_PASSPHRASE)
    salt, nonce = os.urandom(16), os.urandom(12)
    data = AESGCM(_key(passphrase, salt, N, R, P)).encrypt(nonce, json.dumps(values).encode(), AAD)
    return {
        "alg": ALG,
        "kdf": KDF,
        "n": N,
        "r": R,
        "p": P,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "data": _b64(data),
    }


def unseal(box: dict, passphrase: str) -> dict:
    try:
        if box.get("alg") != ALG or box.get("kdf") != KDF:
            raise ValueError("algorithm")
        n, r, p = int(box["n"]), int(box["r"]), int(box["p"])
        if not (2**10 <= n <= 2**20 and 1 <= r <= 16 and 1 <= p <= 4):
            raise ValueError("parameters")  # a file cannot make the server spend minutes deriving a key
        salt, nonce, data = (base64.b64decode(box[k], validate=True) for k in ("salt", "nonce", "data"))
    except (KeyError, TypeError, ValueError):
        raise AppError(422, "config_file_invalid") from None
    try:
        plain = AESGCM(_key(passphrase or "", salt, n, r, p)).decrypt(nonce, data, AAD)
    except InvalidTag:
        raise AppError(422, "config_passphrase_wrong") from None
    values = json.loads(plain)
    if not isinstance(values, dict):
        raise AppError(422, "config_file_invalid")
    return values
