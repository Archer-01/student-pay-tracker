"""Shared test fixtures.

``db_session`` is the fixture every integration test from Sprint 2 onward uses: a fresh,
migration-applied in-memory SQLite database *per test*. Because each test gets its own
throwaway database (disposed at teardown), service code that calls ``session.commit()`` is
naturally isolated — no cross-test leakage, no savepoint bookkeeping.

The migrations run once per session, into a template; each test gets a copy of it through
SQLite's backup API (about a millisecond, where running the chain took ~60 ms a test and most of
the suite's time). The copy is the migrated schema itself, so tests still run against exactly
what the migrations build, never `metadata.create_all`.
"""

import sqlite3
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from alembic import command
from app.api.deps import SESSION_COOKIE, get_db
from app.core import security
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


def _in_memory_engine(creator: Callable[[], sqlite3.Connection] | None = None) -> Engine:
    # StaticPool keeps the one underlying connection alive so the in-memory schema and data
    # persist across sessions/connections; ``dispose()`` throws it all away.
    if creator is None:
        return create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine("sqlite://", creator=creator, poolclass=StaticPool)


@pytest.fixture(scope="session")
def _migrated_template() -> Iterator[sqlite3.Connection]:
    """An in-memory database migrated to head once for the whole run. Never handed to a test."""
    engine = _in_memory_engine()
    with engine.connect() as connection:
        command.upgrade(_alembic_config(connection), "head")
        connection.commit()
        template = connection.connection.driver_connection
        assert isinstance(template, sqlite3.Connection)
        yield template
    engine.dispose()


@pytest.fixture
def db_engine(_migrated_template: sqlite3.Connection) -> Iterator[Engine]:
    """A fresh in-memory SQLite database, migrated to head, for a single test."""

    def copy_of_template() -> sqlite3.Connection:
        fresh = sqlite3.connect(":memory:", check_same_thread=False)
        _migrated_template.backup(fresh)
        return fresh

    # The app's connect hook (app/core/db.py) sets foreign_keys=ON on the copy, as in production.
    engine = _in_memory_engine(copy_of_template)
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


@pytest.fixture(scope="session", autouse=True)
def _plain_cli_output() -> Iterator[None]:
    """The CLI's tests read its output as text. Typer forces colours when `GITHUB_ACTIONS` is set,
    and the codes split words (`--amount` came out wrapped in ANSI codes in CI); a dumb terminal
    gets plain text everywhere."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TERM", "dumb")
        yield


@pytest.fixture(scope="session", autouse=True)
def _cheap_password_hashing() -> Iterator[None]:
    """argon2id at production cost takes ~25 ms by design, and the signed-in `client` pays it
    twice per test (create the account, then sign in). The tests check what hashing does, not
    how slow it is, so they hash at a fraction of the cost: still argon2id, still a real PHC
    string. Above the minimum on purpose, so the rehash test's weaker hash still counts as weaker.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            security, "_hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
        )
        yield


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
