"""Per-request values that infrastructure (audit, logs) needs without threading them through every call."""

from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)
