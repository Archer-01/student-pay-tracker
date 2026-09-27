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
    DuplicateUserError,
    InvalidCredentialsError,
    InvalidPeriodError,
    InvalidWriteoffError,
    NotAuthenticatedError,
    PackInUseError,
    PackNotFoundError,
    StudentNotFoundError,
    TooManyAttemptsError,
    UserNotFoundError,
)

logger = logging.getLogger("app.api")

# Exact-type handlers win over the DomainError fallback (Starlette walks the MRO), so listing a
# subclass here overrides the 400 default. Anything not listed is a 400.
_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    # 401, not 403: the client's move is to sign in, and the SPA's interceptor keys on it.
    (NotAuthenticatedError, 401),
    (InvalidCredentialsError, 401),
    (StudentNotFoundError, 404),
    (ClassNotFoundError, 404),
    (PackNotFoundError, 404),
    (UserNotFoundError, 404),
    (DuplicatePaymentError, 409),
    (DuplicateClassError, 409),
    (ClassNotEmptyError, 409),
    (DuplicatePackError, 409),
    (DuplicateUserError, 409),
    (PackInUseError, 409),
    (InvalidPeriodError, 409),
    (InvalidWriteoffError, 409),
    (TooManyAttemptsError, 429),
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
    # A 429 without Retry-After leaves a client guessing how long to wait; the value is already on
    # the exception, so surface it as the header clients actually look for.
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": exc.code},
        headers=headers,
    )


def _handler(status_code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        return _handle(request, exc, status_code)

    return handle


def register_error_handlers(app: FastAPI) -> None:
    for error_type, status_code in _STATUS_BY_ERROR:
        app.add_exception_handler(error_type, _handler(status_code))
    app.add_exception_handler(DomainError, _handler(_FALLBACK_STATUS))
