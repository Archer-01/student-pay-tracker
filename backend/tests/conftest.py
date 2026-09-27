"""Shared test fixtures.

``db_session`` is the fixture every integration test from Sprint 2 onward uses: a fresh,
migration-applied in-memory SQLite database *per test*. Because each test gets its own
throwaway database (disposed at teardown), service code that calls ``session.commit()`` is
naturally isolated — no cross-test leakage, no savepoint bookkeeping.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from alembic import command
from app.api.deps import SESSION_COOKIE, get_db
from app.core.db import get_auth_db
from app.core.settings import settings
from app.core.throttle import login_throttle
from app.main import app as fastapi_app
from app.models import User
from app.services.auth_service import AuthService

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config(connection: Connection) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    # env.py applies migrations to this exact connection (see run_migrations_online).
    cfg.attributes["connection"] = connection
    return cfg


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite database, migrated to head, for a single test.

    StaticPool keeps the one underlying connection alive so the in-memory schema and data
    persist across sessions/connections within the test; ``dispose()`` throws it all away.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")
        connection.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    session = Session(db_engine)
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# API fixtures (httpx.AsyncClient against the ASGI app, DB pointed at db_engine).
#
# `client` is **signed in**: it seeds a user, mints a session, and presents the cookie. Every
# integration test written before auth landed keeps passing unchanged because of that — the
# alternative was editing twenty files to add a login step that none of them are about.
#
# Use `anonymous_client` for the tests that are specifically about the gate.
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_login_throttle() -> Iterator[None]:
    """The throttle is a process-wide singleton, so failed-login counts would otherwise accumulate
    across the whole suite — every test shares one client IP and a handful of usernames, and the
    tests that deliberately fail a login would eventually start getting 429s from each other."""
    login_throttle.reset()
    yield
    login_throttle.reset()


@pytest.fixture(autouse=True)
def _insecure_cookies_for_http_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests speak plain http, and an httpx cookie jar silently refuses to *send* a cookie marked
    Secure over http — a login would appear to succeed and then every following request would 401.
    This is the same trap as local dev (see `settings.cookie_secure`), so the suite runs the way
    dev does rather than papering over it."""
    monkeypatch.setattr(settings, "cookie_secure", False)


@pytest.fixture
def _override_db(db_engine: Engine) -> Iterator[None]:
    """Point both session dependencies at the one in-memory database.

    In production the central accounts database and each teacher's data are separate files (see
    `app/core/db.py`). Tests collapse them onto one, which they can because a single migration
    chain creates every table in every database — so one in-memory DB holds `user`, `auth_session`
    *and* the domain tables at once.

    That collapse is why no existing test needed editing when data moved into per-teacher files.
    It does mean these fixtures cannot prove the teachers are actually isolated — for that, see
    `test_tenant_isolation.py`, which uses real files.
    """

    def _session() -> Iterator[Session]:
        session = Session(db_engine)
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _session
    fastapi_app.dependency_overrides[get_auth_db] = _session
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_engine: Engine) -> User:
    """A signed-in-able account, created directly through the service the CLI uses."""
    session = Session(db_engine)
    try:
        return AuthService(session).create_user(
            username="teacher", display_name="Teacher", password="correct-horse"
        )
    finally:
        session.close()


@pytest.fixture
async def anonymous_client(_override_db: None) -> AsyncIterator[AsyncClient]:
    """A client with no session cookie — for testing that the gate actually gates."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client(
    _override_db: None, test_user: User, db_engine: Engine
) -> AsyncIterator[AsyncClient]:
    """An authenticated client. The cookie is set from a real session row rather than faked, so
    these tests exercise the same `require_session` path production does."""
    session = Session(db_engine)
    try:
        issued = AuthService(session).login(username="teacher", password="correct-horse")
    finally:
        session.close()

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE: issued.token},
    ) as ac:
        yield ac
