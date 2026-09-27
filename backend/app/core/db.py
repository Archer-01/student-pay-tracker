"""Database wiring: the declarative base, engines, session factories, and SQLite pragmas.

Kept deliberately thin — no domain logic lives here. The service layer owns all business rules;
models and repos stay dumb.

**One database per teacher.** ``settings.database_url`` names the *central* database, which holds
only ``user`` and ``auth_session``. Each account's domain data — students, classes, packs,
payments — lives in its own file alongside it:

    /data/ardoise.db        central: who can sign in
    /data/tenant-1.db       one teacher's students, classes, packs, …
    /data/tenant-2.db       the other's, in a physically separate file

This is how the "each teacher's students are private" rule is enforced. The alternative — an
``owner_id`` column filtered at 21 query sites — puts the guarantee in 21 places that must each
stay correct forever; a separate file puts it in the filesystem, where no forgotten ``WHERE``
clause can leak a row. It also splits the SQLite write lock, so one teacher saving a payment no
longer blocks the other.

Every database gets the **same migration chain**. The central one simply leaves the domain tables
empty and the tenant ones leave ``user``/``auth_session`` empty. That wastes a few empty tables in
exchange for `alembic upgrade head` working against any file, including one created moments ago
for a brand-new account — and no second migration history that can drift out of step with the
first.

Engines are created lazily and cached per URL: importing a model must not require a live database,
so tests and Alembic can import ``Base`` without touching one.
"""

import sqlite3
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Apply SQLite pragmas on every connection.

    - ``foreign_keys=ON``: SQLite ignores FK constraints (incl. ``ON DELETE RESTRICT``) unless
      this is set per connection.
    - ``journal_mode=WAL``: safer concurrent reads and fewer "database is locked" errors
      (ignored/no-op on ``:memory:``, so tests are unaffected).
    - ``synchronous=NORMAL``: a good durability/speed balance under WAL.

    Guarded to real SQLite connections so it's a harmless no-op for any other backend.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def central_url() -> str:
    """The database holding accounts. Whatever ``DATABASE_URL`` points at."""
    return settings.database_url


def tenant_url(user_id: int) -> str:
    """Where this account's domain data lives — a sibling file of the central database.

    Derived rather than configured so there is nothing to keep in sync: adding an account creates
    a file, and removing one leaves a file. An in-memory central URL yields an in-memory tenant
    URL, which is what the test suite relies on.
    """
    url = make_url(central_url())
    if not url.database or url.database == ":memory:":
        return central_url()
    central = Path(url.database)
    return f"sqlite:///{central.with_name(f'tenant-{user_id}.db')}"


# Keyed on a *resolved* URL, never on the `None` default. Caching the default directly would be
# wrong twice over: `get_engine()` and `get_engine(central_url())` would build two engines (two
# connection pools) for one database, and the `None` entry would stay pinned to whatever
# `settings.database_url` happened to be on the first call — so changing it, as every CLI test
# does, would silently keep handing back the old database.
@cache
def _engine_for(url: str) -> Engine:
    return create_engine(url)


@cache
def _sessionmaker_for(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=_engine_for(url), expire_on_commit=False)


def get_engine(url: str | None = None) -> Engine:
    """An engine for ``url``, built once and reused. Defaults to the central database.

    Cached per URL rather than globally: a request for one teacher and a request for the other
    need different engines, and rebuilding them per request would discard the connection pool.
    """
    return _engine_for(url or central_url())


def get_sessionmaker(url: str | None = None) -> sessionmaker[Session]:
    """A session factory bound to :func:`get_engine` for ``url``."""
    return _sessionmaker_for(url or central_url())


def session_for(url: str | None = None) -> Iterator[Session]:
    """Yield a session against ``url``, closing it afterwards."""
    session = get_sessionmaker(url or central_url())()
    try:
        yield session
    finally:
        session.close()


def get_auth_db() -> Iterator[Session]:
    """A session on the **central** database — accounts and sessions only.

    Deliberately separate from the per-teacher session used by the data routes: resolving *who you
    are* has to happen before there is a tenant database to talk to.
    """
    yield from session_for(central_url())


def clear_engine_cache() -> None:
    """Forget every cached engine and session factory.

    Needed wherever the configured URL changes under us — the CLI's test fixtures, and `db reset`.
    """
    _engine_for.cache_clear()
    _sessionmaker_for.cache_clear()
    # Late import: `provisioning` imports this module, so importing it at module scope would be a
    # cycle. Its memo of "which tenant databases are migrated" is keyed by URL and would otherwise
    # survive a repointed `database_url`, which is exactly what this function exists to undo.
    from app.core.provisioning import forget_ready

    forget_ready()
