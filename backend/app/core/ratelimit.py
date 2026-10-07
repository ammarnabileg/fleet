"""Request limits by client address, or by the signed-in user or device (BRD section 8: a limit on requests and OTP
attempts). Counted in PostgreSQL so the four API workers share one count, in fixed windows, and committed on its own
connection: a request that fails still counts, which is the point.

Two kinds: a request that costs something whatever its outcome (a WhatsApp code sent, a file stored) counts every time
(`limited`); a guess (a password, a code, an activation link) counts only when it fails (`failures_limited`), so an
office signing in all day is never stopped, while a script guessing is, right ones included, once over the limit.
Mobile networks put many phones behind one address and on sign-up day every driver comes from the office's:
RATE_LIMIT_EXEMPT lists addresses never limited."""

import ipaddress
import math
import random
from collections.abc import Iterator
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
SEEN = text("SELECT hits FROM identity.rate_hits WHERE bucket = :b AND key = :k AND window_start = :w")
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


def _window(bucket: str) -> tuple[int, datetime, datetime, int]:
    limit, minutes = rules()[bucket]
    now = utcnow()
    span = minutes * 60
    return limit, now, datetime.fromtimestamp(int(now.timestamp()) // span * span, UTC), span


def _refuse(now: datetime, start: datetime, span: int) -> AppError:
    left = (start + timedelta(seconds=span) - now).total_seconds()
    return AppError(429, "too_many_requests", minutes=max(1, math.ceil(left / 60)))


def hit(bucket: str, key: str | None = None) -> None:
    """One request in `bucket` from `key` (the client's address unless given); 429 once over the limit."""
    ip = context.client_ip.get()
    if key is None and exempt(ip):
        return
    limit, now, start, span = _window(bucket)
    with get_engine().begin() as c:
        hits = c.execute(HIT, {"b": bucket, "k": key or ip or "unknown", "w": start}).scalar_one()
        if random.random() < 0.01:  # noqa: S311 - not a secret: how often old windows are swept
            c.execute(SWEEP)
    if hits > limit:
        raise _refuse(now, start, span)


def check(bucket: str) -> None:
    """429 if the client's address has used up `bucket` in this window; counts nothing."""
    ip = context.client_ip.get()
    if exempt(ip):
        return
    limit, now, start, span = _window(bucket)
    with get_engine().connect() as c:
        hits = c.execute(SEEN, {"b": bucket, "k": ip or "unknown", "w": start}).scalar()
    if (hits or 0) >= limit:
        raise _refuse(now, start, span)


def limited(bucket: str):
    """A route dependency: every request counts in `bucket` by the client's address."""

    def dependency() -> None:
        hit(bucket)

    return dependency


def failures_limited(bucket: str):
    """A route dependency for guesses: refused once the address has failed `bucket`'s limit in this window, and a
    request answered with an error (wrong password, wrong code, unknown link) counts; one that succeeds does not."""

    def dependency() -> Iterator[None]:
        check(bucket)
        try:
            yield
        except AppError as e:
            if 400 <= e.status < 500:
                try:
                    hit(bucket)
                except AppError:
                    pass  # this failure was the last allowed: the next request is refused
            raise

    return dependency
