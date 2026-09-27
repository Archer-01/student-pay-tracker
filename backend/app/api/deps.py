"""Shared FastAPI dependencies."""

from collections.abc import Iterator

from fastapi import Cookie, Depends, Header, Query
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_auth_db, session_for
from app.core.i18n import normalize_locale, resolve_locale
from app.core.provisioning import ensure_tenant
from app.models import User
from app.services.auth_service import AuthService

# The session cookie's name. Defined here rather than inline so the router that sets it and the
# dependency that reads it can never disagree about the spelling.
SESSION_COOKIE = "ardoise_session"


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


def require_session(
    db: DbSession = Depends(get_auth_db),
    ardoise_session: str | None = Cookie(None, alias=SESSION_COOKIE),
) -> User:
    """The signed-in user, or ``NotAuthenticatedError`` (-> 401).

    Reads the **central** database: resolving who you are must happen before there is a tenant
    database to open.

    Attached to whole routers in ``main.py`` via ``dependencies=[...]`` rather than to individual
    endpoints, so adding a new route to a gated router is protected by default instead of by
    remembering to annotate it.
    """
    return AuthService(db).resolve(ardoise_session)


def get_db(user: User = Depends(require_session)) -> Iterator[DbSession]:
    """A session on **the signed-in teacher's own database**.

    This is the whole of the privacy guarantee. Every data route already depends on `get_db`, so
    each one silently talks to the right file — there is no `WHERE owner_id = ...` to remember at
    a query site, and no way for a missing one to leak a row, because the other teacher's rows are
    not in the database being queried.

    It lives here rather than in `app.core.db` because it depends on the authenticated user, and
    `core` must not import from `api`.
    """
    # `ensure_tenant` rather than `tenant_url`: SQLite would happily open a *missing* file as an
    # empty database and then 500 on every query, so the file is confirmed migrated first. Memoised
    # per process, so this costs a set lookup after the account's first request.
    yield from session_for(ensure_tenant(user.id))
