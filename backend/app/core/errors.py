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


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        # `params` fill the placeholders of the translated message (namespace "errors", key = code)
        return problem(exc.status, exc.code, exc.detail, **({"params": exc.params} if exc.params else {}))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(422, "validation_error", errors=errors)

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        return problem(
            exc.status_code,
            HTTPStatus(exc.status_code).name.lower(),
            exc.detail if isinstance(exc.detail, str) else None,
        )
