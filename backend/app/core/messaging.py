"""Messages to a driver's phone (the sign-in code), behind one small interface chosen by configuration.

- "whatsapp": WhatsApp through an Evolution API instance.
- "log": development and tests only. It refuses production, so codes never end up in production logs.

Delivery failures raise DeliveryError. The caller still answers the driver the same way (otherwise a failure
would reveal that the phone belongs to a driver) and raises an alert, so supervisors learn the channel is down.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote

import httpx

from app.core.config import get_settings

log = logging.getLogger("fleet.messaging")


class DeliveryError(Exception):
    pass


@dataclass(frozen=True)
class Message:
    to: str
    text: str


class LogProvider:
    def __init__(self) -> None:
        if get_settings().is_production:
            raise RuntimeError("the log messaging provider must not be used in production: set MESSAGING_PROVIDER")
        self.sent: list[Message] = []  # tests read the codes from here

    def send(self, to: str, text: str) -> None:
        self.sent.append(Message(to, text))
        log.info("message to %s: %s", to, text)

    def connection_state(self) -> str:
        return "open"


class EvolutionProvider:
    """WhatsApp through Evolution API (v2): POST /message/sendText/{instance} with the `apikey` header."""

    def __init__(self, url: str, api_key: str, instance: str, *, transport=None, timeout: float = 10.0) -> None:
        self._instance = quote(instance, safe="")
        self._client = httpx.Client(
            base_url=url.rstrip("/"), headers={"apikey": api_key}, timeout=timeout, transport=transport
        )

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DeliveryError(f"evolution api unreachable: {exc.__class__.__name__}") from None
        if response.status_code >= 300:
            raise DeliveryError(f"evolution api answered {response.status_code}")
        return response

    def send(self, to: str, text: str) -> None:
        # Evolution expects the international number without "+": +96550000000 -> 96550000000
        self._call("POST", f"/message/sendText/{self._instance}", json={"number": to.lstrip("+"), "text": text})

    def connection_state(self) -> str:
        """ "open" when the WhatsApp session is connected; "close" or "connecting" when it needs attention."""
        body = self._call("GET", f"/instance/connectionState/{self._instance}").json()
        return str((body.get("instance") or {}).get("state") or body.get("state") or "unknown")


@lru_cache
def provider() -> LogProvider | EvolutionProvider:
    settings = get_settings()
    if settings.messaging_provider == "log":
        return LogProvider()
    if settings.messaging_provider == "whatsapp":
        missing = [
            n for n in ("evolution_api_url", "evolution_api_key", "evolution_instance") if not getattr(settings, n)
        ]
        if missing:
            raise RuntimeError(f"WhatsApp messaging needs {', '.join(m.upper() for m in missing)}")
        return EvolutionProvider(settings.evolution_api_url, settings.evolution_api_key, settings.evolution_instance)
    raise RuntimeError(f"unknown messaging provider {settings.messaging_provider!r}")
