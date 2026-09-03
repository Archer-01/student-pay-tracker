"""Map domain exceptions to HTTP responses (localized) and log each handled error."""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.i18n import normalize_locale, resolve_locale, translate
from app.services.exceptions import (
    ClassNotEmptyError,
    ClassNotFoundError,
    DomainError,
    DuplicateClassError,
    DuplicatePackError,
    DuplicatePaymentError,
    InvalidPeriodError,
    InvalidWriteoffError,
    PackInUseError,
    PackNotFoundError,
    StudentNotFoundError,
)

logger = logging.getLogger("app.api")

# Exact-type handlers win over the DomainError fallback (Starlette walks the MRO), so listing a
# subclass here overrides the 400 default. Anything not listed is a 400.
_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (StudentNotFoundError, 404),
    (ClassNotFoundError, 404),
    (PackNotFoundError, 404),
    (DuplicatePaymentError, 409),
    (DuplicateClassError, 409),
    (ClassNotEmptyError, 409),
    (DuplicatePackError, 409),
    (PackInUseError, 409),
    (InvalidPeriodError, 409),
    (InvalidWriteoffError, 409),
)
_FALLBACK_STATUS = 400


def _handle(request: Request, exc: DomainError, status_code: int) -> JSONResponse:
    key = f"error.{exc.code}"
    locale = normalize_locale(request.query_params.get("lang")) or resolve_locale(
        request.headers.get("accept-language")
    )
    # Log in English (developer-facing) regardless of the response locale.
    logger.warning(
        "%s %s -> %d: %s",
        request.method,
        request.url.path,
        status_code,
        translate(key, "en", **exc.params),
    )
    detail = translate(key, locale, **exc.params)
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": exc.code})


def _handler(status_code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        return _handle(request, exc, status_code)

    return handle


def register_error_handlers(app: FastAPI) -> None:
    for error_type, status_code in _STATUS_BY_ERROR:
        app.add_exception_handler(error_type, _handler(status_code))
    app.add_exception_handler(DomainError, _handler(_FALLBACK_STATUS))
