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


def test_0011_adds_and_removes_billed_from(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'billed_from.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0011")
            columns = {c["name"]: c for c in inspect(connection).get_columns("student")}
            assert columns["billed_from"]["nullable"] is True
            command.downgrade(cfg, "0010")
            assert "billed_from" not in {
                c["name"] for c in inspect(connection).get_columns("student")
            }
    finally:
        engine.dispose()


def test_0012_gives_every_free_student_a_free_period(tmp_path: Path) -> None:
    # Data, not only shape: whoever is free at the upgrade must stay free once priced, and
    # whoever 0011 had marked billed-from keeps exactly those months free.
    engine = create_engine(f"sqlite:///{tmp_path / 'free.db'}")
    cfg = Config(str(_ALEMBIC_INI))
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0011")
            connection.execute(
                text(
                    "INSERT INTO pack (id, name, level, price, is_active) VALUES "
                    "(1, 'Offert', 'TC', 0, 1), (2, 'Maths', 'TC', 200, 1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO student (id, first_name, join_date, status, pack_id, "
                    "custom_price, billed_from) VALUES "
                    "(1, 'Agreed0', '2026-09-05', 'active', NULL, 0, NULL), "
                    "(2, 'Pack0', '2026-09-06', 'active', 1, NULL, NULL), "
                    "(3, 'Pays', '2026-09-07', 'active', 2, NULL, NULL), "
                    "(4, 'Unset', '2026-09-08', 'active', NULL, NULL, NULL), "
                    "(5, 'WasFree', '2026-09-09', 'active', 2, NULL, '2026-11-22'), "
                    "(6, 'Pack0Agreed', '2026-09-10', 'active', 1, 150, NULL)"
                )
            )
            connection.commit()
            command.upgrade(cfg, "0012")
            rows = connection.execute(
                text("SELECT student_id, from_date, to_date FROM free_period ORDER BY student_id")
            ).fetchall()
            assert [tuple(r) for r in rows] == [
                (1, "2026-09-05", None),
                (2, "2026-09-06", None),
                (5, "2026-09-09", "2026-11-22"),
            ]
            assert "billed_from" not in {
                c["name"] for c in inspect(connection).get_columns("student")
            }
            entered = connection.execute(
                text("SELECT count(*) FROM student WHERE entered_on IS NULL")
            )
            assert entered.scalar() == 0  # backfilled from created_at
            command.downgrade(cfg, "0011")
            assert "free_period" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()
