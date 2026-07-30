"""Migration round-trip: upgrade creates every table, downgrade removes them cleanly."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_APP_TABLES = {"student", "payment", "anchor_override"}


def test_upgrade_creates_all_tables_and_downgrade_removes_them(tmp_path: Path) -> None:
    # A throwaway temp-file SQLite DB, isolated from the shared in-memory fixtures.
    # Injecting the connection makes env.py apply migrations to exactly this DB,
    # independent of the ambient DATABASE_URL.
    engine = create_engine(f"sqlite:///{tmp_path / 'migration_test.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection

            command.upgrade(cfg, "head")
            assert _APP_TABLES.issubset(set(inspect(connection).get_table_names()))

            command.downgrade(cfg, "base")
            # No application tables remain (alembic's own version table may persist).
            assert _APP_TABLES.isdisjoint(set(inspect(connection).get_table_names()))
    finally:
        engine.dispose()
