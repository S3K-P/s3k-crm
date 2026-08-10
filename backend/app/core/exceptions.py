"""Application exception hierarchy and HTTP error handlers.

Error responses are structured and deliberately terse: they never expose
connection strings, credentials, driver messages or stack traces to clients.
Full diagnostic detail goes to the structured log instead.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base class for expected, handled application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)

    def to_response(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            body["error"]["details"] = self.details
        return body


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_failed"
    message = "The request payload failed validation."


class ServiceUnavailableError(AppError):
    """A required downstream dependency is unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "A required dependency is currently unavailable."


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "application_error",
        code=exc.code,
        status_code=exc.status_code,
        path=request.url.path,
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_response())


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "validation_failed",
                "message": "The request payload failed validation.",
                "details": {"fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()]},
            }
        },
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log with traceback internally; return an opaque body to the client.
    logger.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the structured error handlers to the application."""
    # Starlette types handlers against the base Exception; the narrower
    # signatures here are what FastAPI actually dispatches.
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        StarletteHTTPException,
        _http_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RequestValidationError,
        _validation_error_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, _unhandled_error_handler)
