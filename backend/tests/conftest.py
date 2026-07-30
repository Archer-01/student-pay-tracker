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
from app.core.db import get_db
from app.main import app as fastapi_app

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
# The API is open (no auth), so a single plain client fixture suffices.
# --------------------------------------------------------------------------- #


@pytest.fixture
def _override_db(db_engine: Engine) -> Iterator[None]:
    def _get_db() -> Iterator[Session]:
        session = Session(db_engine)
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _get_db
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(_override_db: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
