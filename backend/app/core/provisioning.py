"""Creating and migrating databases — the central one and each teacher's.

Separate from ``app.core.db`` because that module must stay importable without alembic on the
path; this one deliberately pulls alembic in.

Migrations are applied through an **injected connection** rather than by pointing alembic at a
URL. ``alembic/env.py`` overwrites ``sqlalchemy.url`` from settings on every run, so setting it
per tenant would be silently undone — but ``config.attributes["connection"]`` takes precedence
over the URL entirely. It is the same path the test suite already uses.
"""

import logging
import threading
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.db import central_url, get_engine, tenant_url

logger = logging.getLogger("app.provisioning")

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _config(connection: object) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    return cfg


def migrate(url: str) -> None:
    """Bring one database up to head, creating the file if it doesn't exist yet."""
    engine = get_engine(url)
    with engine.connect() as connection:
        command.upgrade(_config(connection), "head")
        connection.commit()


def provision_tenant(user_id: int) -> str:
    """Create and migrate a teacher's database. Idempotent — safe on an existing one."""
    url = tenant_url(user_id)
    migrate(url)
    _mark_ready(url)
    return url


# Tenant databases already confirmed to be at head in this process. Purely an optimisation: every
# entry could be dropped and the only cost would be re-running an alembic check.
_ready: set[str] = set()
_ready_lock = threading.Lock()


def _mark_ready(url: str) -> None:
    with _ready_lock:
        _ready.add(url)


def forget_ready() -> None:
    """Drop the memo. For tests, which point the same URLs at different files."""
    with _ready_lock:
        _ready.clear()


def ensure_tenant(user_id: int) -> str:
    """The URL for this teacher's database, guaranteed to exist and be migrated.

    Called on the request path, so it memoises: after the first request for an account it is a set
    lookup, not an alembic round-trip.

    It exists because the failure it prevents is nasty and silent. SQLite *creates* a database file
    on connect, so a teacher whose file was never built doesn't get a helpful error — they get an
    empty database and `no such table: student` (a 500) on every single page. That can happen when
    `users add` creates the account but fails to build its database, or when a backup restores the
    central file without the tenant ones. Repairing it here means the app heals itself instead of
    needing a restart.
    """
    url = tenant_url(user_id)
    if url in _ready:
        return url
    # Under the lock: sync dependencies run in a threadpool, so two first-requests for the same
    # account really can arrive together, and two alembic runs against one file is not a race
    # worth having.
    with _ready_lock:
        if url in _ready:
            return url
        migrate(url)
        _ready.add(url)
    return url


def migrate_all(user_ids: list[int]) -> list[int]:
    """Migrate the central database and every teacher's, returning the ones that failed.

    Re-running the central migration here is intentional and free (alembic checks the version
    table first) — it keeps this function correct when called on its own, e.g. from the CLI.

    A tenant that fails to migrate must not stop the app from booting: the other teacher is
    unaffected and should still be able to work. The failure surfaces when the broken account
    tries to sign in, and is logged loudly here.
    """
    migrate(central_url())
    failed: list[int] = []
    for user_id in user_ids:
        try:
            provision_tenant(user_id)
        except Exception:
            logger.exception("migration failed for tenant %s; that account cannot be used", user_id)
            failed.append(user_id)
    return failed
