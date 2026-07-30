"""CLI tests — typer's CliRunner against a throwaway temp-file SQLite database.

The CLI builds its own engine from ``settings.database_url`` via ``app.core.db``; we point that
at a temp file per test (patching the setting and clearing the cached engine/sessionmaker).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from typer.testing import CliRunner

from alembic import command
from app.cli import app
from app.core import db as db_module
from app.core.settings import settings

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")  # env.py reads the patched url
    yield url
    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()


def _add_student(name: str = "Amina", join: str = "2023-03-05", fee: str = "300") -> None:
    result = runner.invoke(
        app, ["students", "add", "--name", name, "--join-date", join, "--fee", fee]
    )
    assert result.exit_code == 0, result.output


def test_students_add_and_show(cli_db: str) -> None:
    _add_student()
    show = runner.invoke(app, ["students", "show", "1"])
    assert show.exit_code == 0, show.output
    assert "Amina" in show.output


def test_end_to_end_drift_15(cli_db: str) -> None:
    # The headline test: enroll, record three late payments, drift shows as 15 via the CLI.
    _add_student()
    for month in ("2023-04", "2023-05", "2023-06"):
        r = runner.invoke(
            app,
            [
                "payments",
                "record",
                "1",
                "--date",
                f"{month}-10",
                "--amount",
                "300",
                "--for-month",
                month,
            ],
        )
        assert r.exit_code == 0, r.output
    show = runner.invoke(app, ["students", "show", "1"])
    assert show.exit_code == 0, show.output
    assert "15" in show.output


def test_for_month_and_cycle_agree(cli_db: str) -> None:
    _add_student(name="A")
    _add_student(name="B")
    by_month = runner.invoke(
        app,
        [
            "payments",
            "record",
            "1",
            "--date",
            "2023-04-10",
            "--amount",
            "300",
            "--for-month",
            "2023-04",
        ],
    )
    by_cycle = runner.invoke(
        app,
        ["payments", "record", "2", "--date", "2023-04-10", "--amount", "300", "--cycle", "1"],
    )
    assert by_month.exit_code == 0 and by_cycle.exit_code == 0
    assert "cycle 1" in by_month.output and "cycle 1" in by_cycle.output
    assert "due 2023-04-05" in by_month.output
    assert "due 2023-04-05" in by_cycle.output


def test_record_requires_exactly_one_selector(cli_db: str) -> None:
    _add_student()
    base = ["payments", "record", "1", "--date", "2023-04-10", "--amount", "300"]
    assert runner.invoke(app, base).exit_code != 0  # neither
    both = [*base, "--for-month", "2023-04", "--cycle", "1"]
    assert runner.invoke(app, both).exit_code != 0  # both


def test_show_unknown_student_errors(cli_db: str) -> None:
    result = runner.invoke(app, ["students", "show", "999"])
    assert result.exit_code != 0
    assert "999" in result.output


def test_duplicate_payment_errors(cli_db: str) -> None:
    _add_student()
    ok = runner.invoke(
        app, ["payments", "record", "1", "--date", "2023-04-10", "--amount", "300", "--cycle", "1"]
    )
    assert ok.exit_code == 0, ok.output
    dup = runner.invoke(
        app, ["payments", "record", "1", "--date", "2023-04-20", "--amount", "300", "--cycle", "1"]
    )
    assert dup.exit_code != 0


def test_bad_date_errors(cli_db: str) -> None:
    _add_student()
    result = runner.invoke(
        app,
        ["payments", "record", "1", "--date", "not-a-date", "--amount", "300", "--cycle", "1"],
    )
    assert result.exit_code != 0


def test_overrides_create(cli_db: str) -> None:
    _add_student()
    result = runner.invoke(
        app,
        ["overrides", "create", "1", "--new-date", "2023-07-20", "--reason", "agreed shift"],
    )
    assert result.exit_code == 0, result.output
    assert "2023-07-20" in result.output


def test_list_sort_by_drift(cli_db: str) -> None:
    _add_student(name="OnTime")
    _add_student(name="Late")
    # Student 2 pays cycle 1 fifteen days late.
    runner.invoke(
        app, ["payments", "record", "2", "--date", "2023-04-20", "--amount", "300", "--cycle", "1"]
    )
    result = runner.invoke(app, ["students", "list", "--sort-by-drift"])
    assert result.exit_code == 0, result.output
    assert result.output.index("Late") < result.output.index("OnTime")


def test_db_reset_blocked_without_env(cli_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_DB_RESET", raising=False)
    result = runner.invoke(app, ["db", "reset", "--yes"])
    assert result.exit_code != 0
    assert "ALLOW_DB_RESET" in result.output


def test_db_reset_allowed_clears_data(cli_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_DB_RESET", "1")
    _add_student()
    result = runner.invoke(app, ["db", "reset", "--yes"])
    assert result.exit_code == 0, result.output
    # Student 1 is gone after the reset.
    assert runner.invoke(app, ["students", "show", "1"]).exit_code != 0
