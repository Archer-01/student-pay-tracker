"""Migration round-trip: upgrade creates every table, downgrade removes them cleanly."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.models import Base

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
# Every table the models declare, so a new table's downgrade is checked without editing this.
_APP_TABLES = set(Base.metadata.tables)


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
            # env.py suspends foreign-key enforcement while migrations run (table rebuilds need
            # it). Prove each migration still left the data referentially sound, and that
            # enforcement came back on afterwards.
            assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
            assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1

            command.downgrade(cfg, "base")
            # No application tables remain (alembic's own version table may persist).
            assert _APP_TABLES.isdisjoint(set(inspect(connection).get_table_names()))
    finally:
        engine.dispose()


def test_0009_adds_and_removes_the_student_note(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'note.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0009")
            columns = {c["name"]: c for c in inspect(connection).get_columns("student")}
            assert columns["note"]["nullable"] is True
            command.downgrade(cfg, "0008")
            assert "note" not in {c["name"] for c in inspect(connection).get_columns("student")}
    finally:
        engine.dispose()


def test_0010_adds_and_removes_the_school_share_handovers(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'handover.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0010")
            assert "school_share_handover" in inspect(connection).get_table_names()
            command.downgrade(cfg, "0009")
            assert "school_share_handover" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_migrations_match_the_models(tmp_path: Path) -> None:
    # `alembic check`: autogenerate against a migrated database must find nothing to do. A model
    # change without its migration (or the reverse) fails here, not on the next autogenerate.
    engine = create_engine(f"sqlite:///{tmp_path / 'check.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
            command.check(cfg)
    finally:
        engine.dispose()


def test_student_foreign_keys_keep_their_on_delete_rules(tmp_path: Path) -> None:
    # SQLAlchemy can't read these two rules back (they are inline REFERENCES, see `_INLINE_FKS`
    # in alembic/env.py), so `alembic check` skips them. SQLite's own pragma can: this is the
    # test that fails if a rebuild of `student` ever drops them.
    engine = create_engine(f"sqlite:///{tmp_path / 'fks.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
            rules = {
                row._mapping["from"]: (row.table, row.on_delete)
                for row in connection.execute(text("PRAGMA foreign_key_list(student)"))
            }
            assert rules == {
                "class_id": ("school_class", "SET NULL"),
                "pack_id": ("pack", "RESTRICT"),
            }
    finally:
        engine.dispose()


def test_every_migration_downgrades_one_step_and_upgrades_again(tmp_path: Path) -> None:
    # The stairway: for each revision in order, up to it, back one, up again. A downgrade that
    # leaves a table, index or column behind makes the second upgrade fail, which the base/head
    # round trip above can miss when a later migration happens to clean up after it.
    engine = create_engine(f"sqlite:///{tmp_path / 'stairway.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    revisions = [
        s.revision for s in reversed(list(ScriptDirectory.from_config(cfg).walk_revisions()))
    ]
    assert revisions, "no migrations found"
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            for revision in revisions:
                command.upgrade(cfg, revision)
                command.downgrade(cfg, "-1")
                command.upgrade(cfg, revision)
                assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
            assert _APP_TABLES.issubset(set(inspect(connection).get_table_names()))
    finally:
        engine.dispose()
