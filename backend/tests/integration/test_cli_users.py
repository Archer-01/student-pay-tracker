"""`ardoise users ...` — the only way an account gets created.

Worth testing end-to-end rather than trusting the service tests: this is the break-glass path, so
"the CLI is broken" and "nobody can sign in" are the same incident.
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
from app.services.auth_service import AuthService

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
runner = CliRunner()

PASSWORD = "correct-horse"

# Repeated verbatim in a couple of tests; named so the lines stay under the limit.
_ENROL_AMINA = [
    "--user",
    "aymen",
    "students",
    "add",
    "--first-name",
    "Amina",
    "--join-date",
    "2026-01-05",
]


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    db_module.clear_engine_cache()
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")
    yield url
    db_module.clear_engine_cache()


def _add(username: str = "aymen", name: str = "Aymen", password: str = PASSWORD) -> None:
    result = runner.invoke(
        app, ["users", "add", username, "--name", name, "--password", password]
    )
    assert result.exit_code == 0, result.output


def test_add_then_list(cli_db: str) -> None:
    _add()
    result = runner.invoke(app, ["users", "list"])
    assert result.exit_code == 0
    assert "aymen" in result.output
    assert "yes" in result.output


def test_list_with_no_accounts_says_how_to_make_one(cli_db: str) -> None:
    result = runner.invoke(app, ["users", "list"])
    assert result.exit_code == 0
    assert "ardoise users add" in result.output


def test_added_account_can_actually_sign_in(cli_db: str) -> None:
    """The CLI and the API must agree — a CLI-made account is one the API accepts."""
    _add()
    with db_module.get_sessionmaker()() as session:
        assert AuthService(session).login(username="aymen", password=PASSWORD).user.username == (
            "aymen"
        )


def test_add_rejects_a_duplicate(cli_db: str) -> None:
    _add()
    result = runner.invoke(
        app, ["users", "add", "AYMEN", "--name", "Other", "--password", PASSWORD]
    )
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_add_rejects_a_short_password(cli_db: str) -> None:
    result = runner.invoke(app, ["users", "add", "x", "--name", "X", "--password", "short"])
    assert result.exit_code == 1
    assert "at least 8" in result.output


def test_passwd_changes_the_password(cli_db: str) -> None:
    _add()
    result = runner.invoke(app, ["users", "passwd", "aymen", "--password", "a-new-password"])
    assert result.exit_code == 0
    with db_module.get_sessionmaker()() as session:
        assert AuthService(session).login(username="aymen", password="a-new-password")


def test_passwd_rejects_an_unknown_account(cli_db: str) -> None:
    result = runner.invoke(app, ["users", "passwd", "ghost", "--password", "a-new-password"])
    assert result.exit_code == 1
    assert "No account named" in result.output


def test_deactivate_then_activate(cli_db: str) -> None:
    _add()

    assert runner.invoke(app, ["users", "deactivate", "aymen"]).exit_code == 0
    assert "no" in runner.invoke(app, ["users", "list"]).output

    assert runner.invoke(app, ["users", "activate", "aymen"]).exit_code == 0
    with db_module.get_sessionmaker()() as session:
        assert AuthService(session).login(username="aymen", password=PASSWORD)


def test_deactivate_rejects_an_unknown_account(cli_db: str) -> None:
    result = runner.invoke(app, ["users", "deactivate", "ghost"])
    assert result.exit_code == 1
    assert "No account named" in result.output


def test_activate_rejects_an_unknown_account(cli_db: str) -> None:
    result = runner.invoke(app, ["users", "activate", "ghost"])
    assert result.exit_code == 1
    assert "No account named" in result.output


# --- Per-teacher databases --------------------------------------------------- #


def test_adding_an_account_builds_its_database(cli_db: str, tmp_path: Path) -> None:
    _add()
    with db_module.get_sessionmaker()() as session:
        user = AuthService(session).get_user("aymen")
    assert (tmp_path / f"tenant-{user.id}.db").exists()


def test_two_accounts_get_two_databases(cli_db: str, tmp_path: Path) -> None:
    _add("aymen", "Aymen")
    _add("ayoub", "Ayoub")
    assert len(list(tmp_path.glob("tenant-*.db"))) == 2


def test_a_domain_command_refuses_to_guess_which_teacher(cli_db: str) -> None:
    """Writing a student into the wrong teacher's database is not something you'd notice quickly,
    so the CLI asks rather than defaulting."""
    _add()
    result = runner.invoke(
        app, ["students", "add", "--first-name", "Amina", "--join-date", "2026-01-05"]
    )
    assert result.exit_code == 1
    assert "--user" in result.output


def test_a_domain_command_works_with_user(cli_db: str) -> None:
    _add()
    result = runner.invoke(
        app,
        _ENROL_AMINA,
    )
    assert result.exit_code == 0, result.output


def test_each_teacher_sees_only_their_own_students(cli_db: str) -> None:
    _add("aymen", "Aymen")
    _add("ayoub", "Ayoub")
    runner.invoke(
        app,
        _ENROL_AMINA,
    )

    mine = runner.invoke(app, ["--user", "aymen", "students", "list"])
    theirs = runner.invoke(app, ["--user", "ayoub", "students", "list"])
    assert "Amina" in mine.output
    assert "Amina" not in theirs.output


def test_an_unknown_user_is_refused(cli_db: str) -> None:
    result = runner.invoke(app, ["--user", "ghost", "students", "list"])
    assert result.exit_code == 1
    assert "No account named" in result.output


def test_backup_covers_every_database(cli_db: str, tmp_path: Path) -> None:
    """Backing up only the central file would save the list of who can log in and none of the
    students."""
    _add("aymen", "Aymen")
    _add("ayoub", "Ayoub")
    dest = tmp_path / "backups"
    result = runner.invoke(app, ["db", "backup", "--to", str(dest)])
    assert result.exit_code == 0, result.output
    # central + two teachers
    assert len(list(dest.glob("backup-*.db"))) == 3


def test_a_domain_command_heals_a_missing_tenant_database(cli_db: str, tmp_path: Path) -> None:
    """Same self-healing as the API: an account whose database is gone must not produce
    "no such table", which is what SQLite opening a missing file would give.

    The cache clear stands in for a fresh process. Deleting a database file that an *already
    running* process has open does not fail — the pooled connection keeps using the unlinked inode
    until it is closed — so without this the command would quietly succeed against a ghost file and
    the test would prove nothing.
    """
    _add()
    with db_module.get_sessionmaker()() as session:
        user_id = AuthService(session).get_user("aymen").id

    tenant = tmp_path / f"tenant-{user_id}.db"
    tenant.unlink()
    db_module.clear_engine_cache()  # also forgets the "already migrated" memo

    result = runner.invoke(app, ["--user", "aymen", "students", "list"])
    assert result.exit_code == 0, result.output
    assert tenant.exists()
