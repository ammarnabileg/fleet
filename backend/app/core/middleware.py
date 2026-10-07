import logging
import time
import uuid

from fastapi import FastAPI, Request

from app.core import context

log = logging.getLogger("fleet.request")


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        context.request_id.set(rid)
        context.client_ip.set(request.client.host if request.client else None)
        context.user_agent.set((request.headers.get("user-agent") or "")[:200] or None)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        log.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            extra={"request_id": rid},
        )
        return response
