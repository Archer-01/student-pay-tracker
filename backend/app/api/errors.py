"""Map domain exceptions to HTTP responses (localized) and log each handled error."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.i18n import normalize_locale, resolve_locale, translate
from app.services.exceptions import DomainError, DuplicatePaymentError, StudentNotFoundError

logger = logging.getLogger("app.api")


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


async def _student_not_found(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return _handle(request, exc, 404)


async def _duplicate_payment(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return _handle(request, exc, 409)


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return _handle(request, exc, 400)


def register_error_handlers(app: FastAPI) -> None:
    # Exact-type handlers win over the DomainError fallback (Starlette walks the MRO).
    app.add_exception_handler(StudentNotFoundError, _student_not_found)
    app.add_exception_handler(DuplicatePaymentError, _duplicate_payment)
    app.add_exception_handler(DomainError, _domain_error)
