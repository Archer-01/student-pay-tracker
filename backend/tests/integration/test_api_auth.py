"""The HTTP surface of sign-in, and the gate over every data route.

The gate test is table-driven over one route per router: it's checking the wiring in `main.py`,
not the endpoints, so one representative route per `include_router` call is the right granularity.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE
from app.core.throttle import MAX_FAILURES
from app.models import User
from app.services.auth_service import AuthService

PASSWORD = "correct-horse"

# One route per gated router in main.py. If a router is added there without a line here, the
# "every router is covered" test below fails.
GATED_ROUTES = [
    "/api/v1/students",
    "/api/v1/classes",
    "/api/v1/packs",
    "/api/v1/debts",
    "/api/v1/dashboard/summary",
    "/api/v1/reports/monthly?year=2026&month=1",
]


# --- The gate --------------------------------------------------------------- #


@pytest.mark.parametrize("route", GATED_ROUTES)
async def test_data_routes_401_without_a_session(anonymous_client: AsyncClient, route: str) -> None:
    assert (await anonymous_client.get(route)).status_code == 401


@pytest.mark.parametrize("route", GATED_ROUTES)
async def test_data_routes_are_reachable_with_a_session(client: AsyncClient, route: str) -> None:
    assert (await client.get(route)).status_code == 200


async def test_every_gated_router_has_a_route_in_this_test() -> None:
    """Guards against a new router being mounted in main.py without gate coverage here.

    Reads the OpenAPI schema rather than walking `app.routes`: FastAPI keeps included routers
    nested rather than flattened, and the shape of that internal structure has changed between
    versions. The published schema is the stable view.
    """
    from app.main import app

    mounted = {
        path.split("/")[3] for path in app.openapi()["paths"] if path.startswith("/api/v1/")
    }
    # `auth` is deliberately ungated (login can't require a login), so it's expected here.
    covered = {route.split("/")[3].split("?")[0] for route in GATED_ROUTES} | {"auth"}
    assert mounted == covered, f"routers without gate coverage: {mounted - covered}"


async def test_a_write_route_401s_without_a_session(anonymous_client: AsyncClient) -> None:
    """Mutations are gated too — not just the reads that happen to be listed above."""
    response = await anonymous_client.post(
        "/api/v1/students", json={"first_name": "X", "join_date": "2026-01-01"}
    )
    assert response.status_code == 401


async def test_health_stays_open(anonymous_client: AsyncClient) -> None:
    """The Docker healthcheck has no session and must never need one."""
    assert (await anonymous_client.get("/health")).status_code == 200


async def test_a_garbage_cookie_is_rejected(anonymous_client: AsyncClient) -> None:
    anonymous_client.cookies.set(SESSION_COOKIE, "not-a-real-token")
    assert (await anonymous_client.get("/api/v1/students")).status_code == 401


# --- Login / logout / me ---------------------------------------------------- #


async def test_login_sets_an_httponly_session_cookie(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "teacher"
    assert response.json()["display_name"] == "Teacher"

    set_cookie = response.headers["set-cookie"]
    assert SESSION_COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


async def test_login_response_never_leaks_the_password_hash(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    assert "password_hash" not in response.json()
    assert "password" not in response.json()


async def test_login_then_data_route_works_end_to_end(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    """The cookie the client receives is the one that opens the gate — no fixture shortcuts."""
    await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    assert (await anonymous_client.get("/api/v1/students")).status_code == 200


async def test_login_rejects_a_wrong_password(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_login_gives_the_same_answer_for_an_unknown_user(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    """Identical body and status to a wrong password, so usernames can't be enumerated."""
    wrong_password = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": "wrong-password"}
    )
    unknown_user = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "ghost", "password": PASSWORD}
    )
    assert unknown_user.status_code == wrong_password.status_code
    assert unknown_user.json() == wrong_password.json()


async def test_login_error_is_localized(anonymous_client: AsyncClient, test_user: User) -> None:
    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"username": "teacher", "password": "wrong-password"},
        headers={"Accept-Language": "fr"},
    )
    assert response.json()["detail"] == "Nom d'utilisateur ou mot de passe incorrect"


async def test_me_returns_the_signed_in_user(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "teacher"


async def test_me_401s_when_signed_out(anonymous_client: AsyncClient) -> None:
    """This is the SPA's "should I show the login page?" probe."""
    response = await anonymous_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


async def test_logout_clears_the_cookie_and_the_session(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/students")).status_code == 401


async def test_logout_without_a_session_is_not_an_error(anonymous_client: AsyncClient) -> None:
    assert (await anonymous_client.post("/api/v1/auth/logout")).status_code == 204


async def test_logout_does_not_sign_out_other_devices(
    anonymous_client: AsyncClient, db_engine, test_user: User
) -> None:
    session = Session(db_engine)
    try:
        other_device = AuthService(session).login(username="teacher", password=PASSWORD)
    finally:
        session.close()

    await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    await anonymous_client.post("/api/v1/auth/logout")

    anonymous_client.cookies.set(SESSION_COOKIE, other_device.token)
    assert (await anonymous_client.get("/api/v1/auth/me")).status_code == 200


# --- Brute-force throttling -------------------------------------------------- #


async def _fail_login(client: AsyncClient, times: int, username: str = "teacher") -> int:
    """Burn `times` wrong passwords; returns the last status code."""
    status = 0
    for _ in range(times):
        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": "wrong-password"}
        )
        status = response.status_code
    return status


async def test_repeated_wrong_passwords_eventually_get_429(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    """argon2id only makes guessing slow; this is what makes it stop."""
    assert await _fail_login(anonymous_client, MAX_FAILURES) == 401
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": "wrong-password"}
    )
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_attempts"


async def test_the_429_carries_a_retry_after_header(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    await _fail_login(anonymous_client, MAX_FAILURES)
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": "wrong-password"}
    )
    assert int(response.headers["Retry-After"]) > 0


async def test_the_lockout_blocks_the_correct_password_too(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    """A lock that the right password walks through would not be a lock."""
    await _fail_login(anonymous_client, MAX_FAILURES)
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    assert response.status_code == 429


async def test_a_few_wrong_attempts_still_allow_signing_in(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    """Mistyping a password you know must not cost you the account for 15 minutes."""
    await _fail_login(anonymous_client, MAX_FAILURES - 1)
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    assert response.status_code == 200


async def test_a_successful_sign_in_resets_the_counter(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    await _fail_login(anonymous_client, MAX_FAILURES - 1)
    await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "teacher", "password": PASSWORD}
    )
    # Without the reset, one more failure would trip the lock.
    assert await _fail_login(anonymous_client, MAX_FAILURES - 1) == 401


async def test_throttling_one_account_does_not_lock_another(
    anonymous_client: AsyncClient, db_engine, test_user: User
) -> None:
    session = Session(db_engine)
    try:
        AuthService(session).create_user(
            username="ayoub", display_name="Ayoub", password=PASSWORD
        )
    finally:
        session.close()

    await _fail_login(anonymous_client, MAX_FAILURES, username="teacher")

    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"username": "ayoub", "password": PASSWORD}
    )
    assert response.status_code == 200


async def test_the_throttle_message_is_localized(
    anonymous_client: AsyncClient, test_user: User
) -> None:
    await _fail_login(anonymous_client, MAX_FAILURES)
    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"username": "teacher", "password": "wrong-password"},
        headers={"Accept-Language": "fr"},
    )
    assert "Trop de tentatives" in response.json()["detail"]


# --- Docs are gated too ------------------------------------------------------ #


@pytest.mark.parametrize("route", ["/openapi.json", "/docs", "/redoc"])
async def test_docs_require_a_session(anonymous_client: AsyncClient, route: str) -> None:
    """The schema leaks no student data, but it maps the API for anyone who can't sign in."""
    assert (await anonymous_client.get(route)).status_code == 401


@pytest.mark.parametrize("route", ["/openapi.json", "/docs", "/redoc"])
async def test_docs_work_when_signed_in(client: AsyncClient, route: str) -> None:
    assert (await client.get(route)).status_code == 200


async def test_the_gated_schema_is_still_the_real_one(client: AsyncClient) -> None:
    """Guards the re-registration in main.py: it must serve the app's schema, not an empty stub."""
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert "/api/v1/students" in paths
