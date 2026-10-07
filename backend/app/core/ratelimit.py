"""Request limits by client address, or by the signed-in user or device (BRD section 8: a limit on requests and OTP
attempts). Counted in PostgreSQL so the four API workers share one count, in fixed windows. A hit is committed on its
own connection before the request runs: a wrong password or an unknown phone still counts, which is the point.

Mobile networks put many phones behind one address, and on the day drivers are signed up together at the office they
all come from its address: the defaults leave room for that, and RATE_LIMIT_EXEMPT lists addresses never limited."""

import ipaddress
import math
import random
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import text

from app.core import context
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import AppError

HIT = text(
    "INSERT INTO identity.rate_hits AS r (bucket, key, window_start, hits) VALUES (:b, :k, :w, 1) "
    "ON CONFLICT (bucket, key, window_start) DO UPDATE SET hits = r.hits + 1 RETURNING r.hits"
)
SWEEP = text("DELETE FROM identity.rate_hits WHERE window_start < now() - interval '1 day'")


def rules() -> dict[str, tuple[int, int]]:
    """bucket: (requests allowed, per so many minutes)."""
    s = get_settings()
    return {
        "sign_in": (s.rate_sign_in_per_15min, 15),  # office sign-in, its second factor, a driver's activation link
        "otp_send": (s.rate_otp_send_per_hour, 60),  # each one is a WhatsApp message
        "otp_check": (s.rate_otp_check_per_15min, 15),
        "upload": (s.rate_uploads_per_hour, 60),  # per user or device, not per address
    }


@lru_cache
def _exempt(raw: str) -> tuple:
    return tuple(ipaddress.ip_network(x.strip(), strict=False) for x in raw.split(",") if x.strip())


def exempt(ip: str | None) -> bool:
    nets = _exempt(get_settings().rate_limit_exempt)
    if not ip or not nets:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in n for n in nets)


def hit(bucket: str, key: str | None = None) -> None:
    """One request in `bucket` from `key` (the client's address unless given); 429 once over the limit."""
    ip = context.client_ip.get()
    if key is None and exempt(ip):
        return
    limit, minutes = rules()[bucket]
    now = utcnow()
    span = minutes * 60
    start = datetime.fromtimestamp(int(now.timestamp()) // span * span, UTC)
    with get_engine().begin() as c:
        hits = c.execute(HIT, {"b": bucket, "k": key or ip or "unknown", "w": start}).scalar_one()
        if random.random() < 0.01:  # noqa: S311 - not a secret: how often old windows are swept
            c.execute(SWEEP)
    if hits > limit:
        left = (start + timedelta(seconds=span) - now).total_seconds()
        raise AppError(429, "too_many_requests", minutes=max(1, math.ceil(left / 60)))


def limited(bucket: str):
    """A route dependency: the request counts in `bucket` by the client's address."""

    def dependency() -> None:
        hit(bucket)

    return dependency
