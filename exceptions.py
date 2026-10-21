"""Domain exceptions and unified error handlers."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("doumitt.errors")


class DoumittBaseException(Exception):
    """Base class for every predictable business error."""

    status_code: int = 400
    code: str = "doumitt_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details


class NotFoundError(DoumittBaseException):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(DoumittBaseException):
    status_code = 403
    code = "permission_denied"


class ConflictError(DoumittBaseException):
    status_code = 409
    code = "conflict"


class InsufficientStockError(DoumittBaseException):
    status_code = 400
    code = "insufficient_stock"


class CurrencyError(DoumittBaseException):
    status_code = 422
    code = "currency_error"


class AuthenticationError(DoumittBaseException):
    status_code = 401
    code = "authentication_error"


class BackgroundTaskError(DoumittBaseException):
    status_code = 503
    code = "background_unavailable"


def error_payload(code: str, message: str, details: Any = None) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach unified JSON handlers to the application."""

    @app.exception_handler(DoumittBaseException)
    async def doumitt_exception_handler(_: Request, exc: DoumittBaseException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "validation_error",
                "بيانات الطلب غير صالحة، يرجى مراجعة الحقول المدخلة.",
                jsonable_encoder(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "حدث خطأ في الطلب."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload("http_error", detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=error_payload(
                "rate_limited",
                "تم تجاوز الحد المسموح من الطلبات. يرجى المحاولة لاحقاً.",
                str(exc.detail),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exc)
        except Exception:  # pragma: no cover - sentry is optional
            pass
        return JSONResponse(
            status_code=500,
            content=error_payload("internal_error", "حدث خطأ غير متوقع في الخادم."),
        )
