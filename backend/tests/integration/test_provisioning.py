"""Creating and migrating per-teacher databases."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.core import db as db_module
from app.core.db import central_url, get_engine, tenant_url
from app.core.provisioning import migrate, migrate_all, provision_tenant
from app.core.settings import settings


@pytest.fixture
def central(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'central.db'}")
    db_module.clear_engine_cache()
    migrate(central_url())
    yield tmp_path
    db_module.clear_engine_cache()


def test_tenant_urls_are_siblings_of_the_central_one(central: Path) -> None:
    assert tenant_url(1) == f"sqlite:///{central / 'tenant-1.db'}"
    assert tenant_url(2) == f"sqlite:///{central / 'tenant-2.db'}"


def test_an_in_memory_central_url_yields_an_in_memory_tenant_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What lets the test suite collapse both onto one database."""
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    assert tenant_url(1) == "sqlite://"


def test_provisioning_creates_a_migrated_database(central: Path) -> None:
    provision_tenant(7)
    assert (central / "tenant-7.db").exists()

    tables = set(inspect(get_engine(tenant_url(7))).get_table_names())
    assert {"student", "school_class", "pack", "payment"} <= tables


def test_provisioning_is_idempotent(central: Path) -> None:
    """Startup re-runs it for every account, so a second call must be a no-op, not an error."""
    provision_tenant(7)
    provision_tenant(7)
    assert (central / "tenant-7.db").exists()


def test_every_database_carries_the_whole_schema(central: Path) -> None:
    """One migration chain runs everywhere, so a tenant has empty `user`/`auth_session` tables and
    the central one has empty domain tables. Wasteful, deliberately — it means `upgrade head`
    works against any file, including one created seconds ago."""
    provision_tenant(7)
    tenant_tables = set(inspect(get_engine(tenant_url(7))).get_table_names())
    central_tables = set(inspect(get_engine(central_url())).get_table_names())
    assert "user" in tenant_tables
    assert "student" in central_tables


def test_migrate_all_reports_failures_without_raising(
    central: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One teacher's broken database must not stop the app from booting for the other."""
    import app.core.provisioning as provisioning

    def _explode(user_id: int) -> str:
        if user_id == 2:
            raise RuntimeError("disk on fire")
        return provisioning.tenant_url(user_id)

    monkeypatch.setattr(provisioning, "provision_tenant", _explode)
    assert migrate_all([1, 2, 3]) == [2]


# --- Self-healing --------------------------------------------------------- #


def test_ensure_tenant_builds_a_database_that_was_never_provisioned(central: Path) -> None:
    """The failure this prevents is silent and total: SQLite opens a *missing* file as an empty
    database, so without this a teacher whose file was never built gets `no such table: student`
    — a 500 on every page — rather than anything diagnosable."""
    from app.core.provisioning import ensure_tenant, forget_ready
    from app.repos import StudentRepo

    forget_ready()
    assert not (central / "tenant-9.db").exists()

    url = ensure_tenant(9)
    with db_module.get_sessionmaker(url)() as session:
        assert StudentRepo(session).list() == []
    assert (central / "tenant-9.db").exists()


def test_ensure_tenant_repairs_an_empty_file(central: Path) -> None:
    """A file can exist and still be useless — an interrupted provision, or a restore that brought
    back the central database but not the tenant ones."""
    from app.core.provisioning import ensure_tenant, forget_ready
    from app.repos import StudentRepo

    forget_ready()
    (central / "tenant-9.db").touch()

    url = ensure_tenant(9)
    with db_module.get_sessionmaker(url)() as session:
        assert StudentRepo(session).list() == []


def test_ensure_tenant_is_memoised(central: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """It sits on the request path, so it must not run alembic on every call."""
    import app.core.provisioning as provisioning

    provisioning.forget_ready()
    calls: list[str] = []
    real = provisioning.migrate
    monkeypatch.setattr(
        provisioning, "migrate", lambda url: (calls.append(url), real(url))[1]
    )

    provisioning.ensure_tenant(9)
    provisioning.ensure_tenant(9)
    provisioning.ensure_tenant(9)
    assert len(calls) == 1


# --- Engine caching ------------------------------------------------------- #


def test_one_engine_per_database_regardless_of_how_it_is_asked_for(central: Path) -> None:
    """`get_engine()` and `get_engine(central_url())` name the same database; two engines would
    mean two connection pools for one SQLite file."""
    assert get_engine() is get_engine(central_url())


def test_the_default_engine_follows_a_changed_url(
    central: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Caching the `None` default directly would pin it to whatever the URL was on first call —
    so every CLI test, which repoints `database_url` at a temp file, would keep talking to the
    database from whichever test ran first."""
    get_engine()  # prime the cache against the fixture's URL
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'other.db'}")
    assert str(get_engine().url).endswith("other.db")
