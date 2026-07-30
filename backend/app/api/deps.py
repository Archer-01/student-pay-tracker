"""Shared FastAPI dependencies."""

from fastapi import Header, Query

from app.core.i18n import normalize_locale, resolve_locale


def get_locale(
    lang: str | None = Query(
        None, description="Force a locale (en/fr); overrides Accept-Language."
    ),
    accept_language: str | None = Header(None),
) -> str:
    """Resolve the locale: explicit ``?lang=`` wins, else ``Accept-Language``, else the default."""
    if lang:
        return normalize_locale(lang) or resolve_locale(None)
    return resolve_locale(accept_language)
