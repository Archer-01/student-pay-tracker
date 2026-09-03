"""Backup: online copy round-trips row counts; rejects non-file sources; CLI smoke."""

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from alembic import command
from app.cli import app as cli_app
from app.core import db as db_module
from app.core.backup import backup_database
from app.core.settings import settings
from app.services.student_service import StudentService

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _migrate_file_db(url: str) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        cfg = Config(str(_ALEMBIC_INI))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
    engine.dispose()


def test_backup_round_trip_preserves_rows(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'src.db'}"
    _migrate_file_db(url)
    engine = create_engine(url)
    with Session(engine) as session:
        StudentService(session).enroll(
            first_name="Amina", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("300")
        )
    engine.dispose()

    dest = backup_database(url, tmp_path / "backups")
    assert dest.exists()

    conn = sqlite3.connect(dest)
    try:
        count = conn.execute("SELECT COUNT(*) FROM student").fetchone()[0]
    finally:
        conn.close()
    assert count == 1


def test_backup_rejects_in_memory() -> None:
    with pytest.raises(ValueError):
        backup_database("sqlite://", Path("/tmp/does-not-matter"))


def test_backup_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        backup_database(f"sqlite:///{tmp_path / 'nope.db'}", tmp_path / "b")


def test_backup_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()
    _migrate_file_db(url)

    result = CliRunner().invoke(cli_app, ["db", "backup", "--to", str(tmp_path / "backups")])
    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()

    assert result.exit_code == 0, result.output
    assert list((tmp_path / "backups").glob("backup-*.db"))
