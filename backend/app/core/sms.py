"""Outgoing SMS behind one small interface; the provider is chosen by configuration.

Only the "log" provider exists until the client picks a gateway. It refuses to run in production, so OTP codes
can never end up in production logs.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings

log = logging.getLogger("fleet.sms")


@dataclass(frozen=True)
class Sms:
    to: str
    text: str


class LogProvider:
    def __init__(self) -> None:
        self.sent: list[Sms] = []  # tests read the codes from here

    def send(self, to: str, text: str) -> None:
        if get_settings().is_production:
            raise RuntimeError("the log SMS provider must not be used in production: configure SMS_PROVIDER")
        self.sent.append(Sms(to, text))
        log.info("sms to %s: %s", to, text)


@lru_cache
def provider() -> LogProvider:
    name = get_settings().sms_provider
    if name != "log":
        raise RuntimeError(f"unknown SMS provider {name!r}")
    return LogProvider()
