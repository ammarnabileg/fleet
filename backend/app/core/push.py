"""Push notifications to the driver app through Firebase Cloud Messaging (HTTP v1), with no Google library: a service
account's private key signs a short JWT, exchanged for an access token (cached until it nearly expires), then one
POST per message. The service account JSON is entered in the control panel (integrations) and kept encrypted.

Failures raise PushError; InvalidToken means the phone's token no longer exists (app removed or reinstalled), so the
caller forgets it instead of trying again."""

import base64
import json
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (an address, not a secret)
FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


class PushError(Exception):
    pass


class InvalidToken(PushError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def parse_service_account(raw: str) -> dict:
    """The JSON key downloaded from Firebase (Project settings > Service accounts); PushError if it is not one."""
    try:
        key = json.loads(raw)
    except ValueError:
        raise PushError("the service account is not JSON") from None
    if not isinstance(key, dict) or not all(key.get(f) for f in ("project_id", "client_email", "private_key")):
        raise PushError("the service account lacks project_id, client_email or private_key")
    try:
        serialization.load_pem_private_key(key["private_key"].encode(), password=None)
    except (ValueError, TypeError):
        raise PushError("the service account's private key cannot be read") from None
    return key


class FcmSender:
    def __init__(self, service_account: str, *, transport=None, timeout: float = 10.0) -> None:
        self._key = parse_service_account(service_account)
        self._private = serialization.load_pem_private_key(self._key["private_key"].encode(), password=None)
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._token: tuple[str, float] | None = None

    @property
    def project_id(self) -> str:
        return self._key["project_id"]

    def _assertion(self) -> str:
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": self._key["client_email"],
            "scope": SCOPE,
            "aud": self._key.get("token_uri") or TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }
        signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
        signature = self._private.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{signing}.{_b64(signature)}"

    def _access_token(self) -> str:
        if self._token and self._token[1] > time.monotonic():
            return self._token[0]
        try:
            r = self._client.post(
                self._key.get("token_uri") or TOKEN_URL,
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self._assertion()},
            )
        except httpx.HTTPError as exc:
            raise PushError(f"token request failed: {exc}") from None
        if r.status_code != 200:
            raise PushError(f"token refused ({r.status_code}): {r.text[:200]}")
        body = r.json()
        self._token = (body["access_token"], time.monotonic() + int(body.get("expires_in", 3600)) - 120)
        return self._token[0]

    def check(self) -> None:
        """The key is accepted by Google (the panel's test): an access token is issued."""
        self._token = None
        self._access_token()

    def send(self, token: str, *, title: str, body: str, data: dict[str, str] | None = None) -> None:
        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": data or {},
                "android": {"priority": "high"},
            }
        }
        try:
            r = self._client.post(
                FCM_URL.format(project=self.project_id),
                json=message,
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
        except httpx.HTTPError as exc:
            raise PushError(f"send failed: {exc}") from None
        if r.status_code == 200:
            return
        if r.status_code == 404 or "UNREGISTERED" in r.text or ("INVALID_ARGUMENT" in r.text and "token" in r.text):
            raise InvalidToken(r.text[:200])
        if r.status_code == 401:
            self._token = None  # expired early: the next message asks again
        raise PushError(f"FCM refused ({r.status_code}): {r.text[:200]}")
