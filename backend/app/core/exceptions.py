"""Typed application exceptions and their FastAPI error handlers.

All errors returned to clients follow the shape:

    {"error": {"code": ..., "message": ..., "details": {...}, "request_id": ...}}

No stack traces, driver internals, or credentials are ever exposed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.exceptions")


class AppError(Exception):
    """Base class for all application-raised, client-facing errors."""

    code: str = "INTERNAL_ERROR"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(AppError):
    code = "ENTITY_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class InvalidInputError(AppError):
    code = "INVALID_INPUT"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class InvalidDateRangeError(AppError):
    code = "INVALID_DATE_RANGE"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class UnsupportedFraudRuleError(AppError):
    code = "UNSUPPORTED_FRAUD_RULE"
    status_code = status.HTTP_400_BAD_REQUEST


class GraphUnavailableError(AppError):
    code = "GRAPH_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class GraphQueryError(AppError):
    code = "GRAPH_QUERY_ERROR"
    status_code = status.HTTP_502_BAD_GATEWAY


class GraphProjectionError(AppError):
    code = "GRAPH_PROJECTION_ERROR"
    status_code = status.HTTP_502_BAD_GATEWAY


def _error_body(code: str, message: str, details: dict[str, Any], request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.warning("app_error code=%s request_id=%s message=%s", exc.code, request_id, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "VALIDATION_ERROR",
                "Request validation failed.",
                {"errors": exc.errors()},
                request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("unhandled_error request_id=%s", request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "INTERNAL_ERROR",
                "An unexpected error occurred.",
                {},
                request_id,
            ),
        )
