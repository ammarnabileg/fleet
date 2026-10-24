from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

PROBLEM = "application/problem+json"


class AppError(Exception):
    """An expected failure with a stable `code` the clients can rely on."""

    def __init__(self, status: int, error_code: str, detail: str | None = None, /, **params):
        super().__init__(error_code)
        self.status, self.code, self.detail, self.params = status, error_code, detail, params


def problem(status: int, code: str, detail: str | None = None, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status, "code": code}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def fallback_message(request: Request, code: str, params: dict | None) -> dict:
    """`message_key` (the app translates it locally, filling `params`) and `message`, a ready text in the request's
    language (the shipped catalogs: English when the language is unknown) for a client without its own texts."""
    import re

    from app.modules.i18n import store

    tag = (request.headers.get("accept-language") or "").split(",")[0].split(";")[0].strip().split("-")[0].lower()
    texts = store.base_catalog(tag).get("errors", {}) if re.fullmatch(r"[a-z]{2,3}", tag or "") else {}
    text = texts.get(code) or store.base_catalog("en").get("errors", {}).get(code) or code
    values = params or {}
    message = re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)
    return {"message_key": f"errors.{code}", "message": message}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        # `params` fill the placeholders of the translated message (namespace "errors", key = code)
        extra = fallback_message(request, exc.code, exc.params)
        return problem(exc.status, exc.code, exc.detail, **extra, **({"params": exc.params} if exc.params else {}))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(422, "validation_error", errors=errors, **fallback_message(request, "validation_error", None))

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        code = HTTPStatus(exc.status_code).name.lower()
        return problem(
            exc.status_code,
            code,
            exc.detail if isinstance(exc.detail, str) else None,
            **fallback_message(request, code, None),
        )
