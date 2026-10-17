"""Central error type + handlers that render the error envelope."""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("rzn.errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, errors: dict[str, Any] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.errors = status, code, message, errors


def not_found(what: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what.capitalize()} not found")


def forbidden(message: str = "You are not allowed to do this") -> AppError:
    return AppError(403, "FORBIDDEN", message)


def invalid_state(message: str) -> AppError:
    return AppError(409, "INVALID_STATE", message)


def validation(message: str, errors: dict[str, Any] | None = None) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message, errors)


def _body(request: Request, code: str, message: str, errors: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {"message": message, "code": code, "request_id": getattr(request.state, "request_id", None)}
    if errors:
        meta["errors"] = errors
    return {"data": None, "meta": meta}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(request, exc.code, exc.message, exc.errors), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: dict[str, list[str]] = {}
        for e in exc.errors():
            field = ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
            errors.setdefault(field or "_", []).append(e["msg"])
        return JSONResponse(_body(request, "VALIDATION_ERROR", "Invalid input", errors), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(request, code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(_body(request, "INTERNAL_ERROR", "Server error, please try again"), status_code=500)
