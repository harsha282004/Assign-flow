"""Uniform error envelope (architecture §20.1) and exception handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.storage import StorageUnavailable

logger = logging.getLogger("assignflow.errors")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        http_status: int,
        message: str,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


def error_response(
    status: int, code: str, message: str, details: dict | None = None, headers: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


def service_unavailable() -> AppError:
    return AppError("SERVICE_UNAVAILABLE", 503, "A required service is temporarily unavailable.")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.http_status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Only location + message: pydantic's "input" would echo submitted values (e.g. passwords).
        problems = [
            {"field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return error_response(422, "VALIDATION_ERROR", "The request is not valid.", {"errors": problems})

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        retry_after = str(exc.limit.limit.get_expiry()) if exc.limit else "60"
        return error_response(
            429,
            "RATE_LIMITED",
            "Too many requests. Please try again later.",
            headers={"Retry-After": retry_after},
        )

    # Fail closed: Redis / database outages surface as 503, never as "allowed" (architecture §19.3, §23).
    @app.exception_handler(RedisError)
    async def _redis_down(_: Request, exc: RedisError) -> JSONResponse:
        logger.error("redis unavailable (%s)", type(exc).__name__)
        err = service_unavailable()
        return error_response(err.http_status, err.code, err.message)

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _db_down(_: Request, exc: Exception) -> JSONResponse:
        logger.error("database error (%s)", type(exc).__name__)
        err = service_unavailable()
        return error_response(err.http_status, err.code, err.message)

    @app.exception_handler(StorageUnavailable)
    async def _storage_down(_: Request, __: StorageUnavailable) -> JSONResponse:
        return error_response(
            503, "STORAGE_UNAVAILABLE", "File storage is temporarily unavailable. Nothing was saved; please try again."
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
