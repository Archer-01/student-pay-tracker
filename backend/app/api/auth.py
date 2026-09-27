"""Sign in, sign out, and "who am I".

These three routes are the only ones under ``/api/v1`` that are **not** gated — the login route
obviously can't require a session, ``/logout`` should work even with a stale cookie, and ``/me``
is how the SPA asks whether it needs to show the login page at all.

The session cookie is ``HttpOnly`` (page scripts can't read it), ``SameSite=Lax`` and ``Secure``
in production. No CSRF token: the SPA is same-origin, every mutation is a ``POST``/``PATCH``/
``DELETE`` sent by ``fetch`` with ``Content-Type: application/json``, and ``SameSite=Lax``
suppresses the cookie on exactly the cross-site requests a form-post attack would use. If a route
is ever added that mutates on ``GET``, or the SPA stops being same-origin, that reasoning lapses
and this needs revisiting.
"""

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import SESSION_COOKIE, require_session
from app.core.db import get_auth_db
from app.core.settings import settings
from app.core.throttle import login_throttle
from app.models import User
from app.schemas.auth import LoginRequest, UserOut
from app.services.auth_service import AuthService
from app.services.exceptions import InvalidCredentialsError, TooManyAttemptsError

# Every route here uses `get_auth_db` (the central accounts database), never the per-teacher
# `get_db`: that one depends on already being authenticated, which is exactly what login
# cannot assume.
router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """The caller's address, for throttling only.

    Reads the socket peer, never `X-Forwarded-For`: a header any client can set is not an identity,
    and trusting it would let an attacker mint a fresh throttle bucket per request. Behind a proxy
    this collapses every caller onto the proxy's address — which, paired with the username half of
    the key, still limits guessing at any one account. If this ever runs behind a proxy where
    per-client limits matter, configure uvicorn's `--proxy-headers` and revisit.
    """
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_auth_db),
) -> User:
    """Exchange a username and password for a session cookie.

    Throttled per (username, IP): argon2id alone only slows guessing down, it doesn't stop it.

    The service call goes through `run_in_threadpool` because argon2id burns ~25ms of CPU by
    design, and this route is `async` — left on the event loop it would stall *every* concurrent
    request for that long, turning the login endpoint into a lever for slowing the whole app.
    """
    ip = _client_ip(request)

    retry_after = login_throttle.retry_after(payload.username, ip)
    if retry_after is not None:
        raise TooManyAttemptsError(retry_after)

    try:
        issued = await run_in_threadpool(
            AuthService(db).login, username=payload.username, password=payload.password
        )
    except InvalidCredentialsError:
        login_throttle.record_failure(payload.username, ip)
        raise

    login_throttle.record_success(payload.username, ip)
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        # Matches the row's TTL, so the cookie lapses when the session does instead of being
        # sent long after the server would reject it.
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        path="/",
    )
    return issued.user


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: DbSession = Depends(get_auth_db),
    ardoise_session: str | None = Cookie(None, alias=SESSION_COOKIE),
) -> None:
    """Drop the session and clear the cookie. Safe to call when already signed out."""
    AuthService(db).logout(ardoise_session)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_session)) -> User:
    """The signed-in user. 401 when there's no valid session — the SPA's "am I logged in?" probe."""
    return user
