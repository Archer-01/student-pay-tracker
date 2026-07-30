"""Database wiring: the declarative base, engine, session factory, and SQLite pragmas.

Kept deliberately thin — no domain logic lives here. The service layer (Sprint 3) owns all
business rules; models and repos stay dumb.

The engine is created lazily (not at import time): importing a model must not require a live
database or DB driver, so tests and Alembic can import ``Base`` without touching a real DB.
"""

import sqlite3
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
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


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """The application engine, built once from ``settings.database_url``."""
    return create_engine(settings.database_url)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """The application session factory, bound to :func:`get_engine`."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Yield an application-bound session (FastAPI dependency, used from Sprint 5)."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
