"""The admin CLI (decision 0010), against throwaway database files.

The CLI only reads a teacher's data (and deletes a student for good), so the data these tests look
at is put in through the services, the way the app's API does. Accounts: test_cli_users.py.
"""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from alembic import command
from app.cli import app
from app.cli._common import money
from app.core import db as db_module
from app.core.provisioning import provision_tenant
from app.core.settings import settings
from app.models import ClassLevel, User
from app.services.class_service import ClassService
from app.services.enrollment_service import EnrollmentService
from app.services.pack_service import PackService
from app.services.payment_service import PaymentService
from app.services.school_share_handover_service import SchoolShareHandoverService
from app.services.student_service import StudentService

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A migrated central database plus one teacher ("cli"), selected via ARDOISE_USER.

    The account row is inserted directly rather than through `AuthService.create_user`, which
    hashes a password nothing here ever checks.
    """
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    db_module.clear_engine_cache()
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")  # env.py reads the patched url

    with db_module.get_sessionmaker()() as session:
        user = User(username="cli", display_name="CLI", password_hash="unused", is_active=True)
        session.add(user)
        session.commit()
        provision_tenant(user.id)

    monkeypatch.setenv("ARDOISE_USER", "cli")
    yield url
    db_module.clear_engine_cache()


def _teacher() -> Session:
    """A session on the "cli" teacher's own database, to put data in as the app would."""
    return db_module.get_sessionmaker(db_module.tenant_url(1))()


def _school(session: Session) -> dict[str, int]:
    """Amina owes two months, Bilal is paid up and late once, Chaima left owing one month.
    All on one 300 DH pack in 2BAC — Groupe A."""
    class_id = ClassService(session).create(level=ClassLevel.BAC2, name="Groupe A").id
    pack = PackService(session).create(
        name="Pack 2BAC", level=ClassLevel.BAC2, price=Decimal("300"), subjects=["Maths"]
    )
    students, payments = StudentService(session), PaymentService(session)

    def enrol(first: str, last: str) -> int:
        return students.enroll(
            first_name=first,
            last_name=last,
            phone="0612345678",
            join_date=date(2026, 9, 5),
            class_id=class_id,
            pack_id=pack.id,
        ).id

    amina, bilal, chaima = (
        enrol("Amina", "Benali"),
        enrol("Bilal", "Tazi"),
        enrol("Chaima", "Idrissi"),
    )
    students.update(amina, note="Paie le samedi")
    for cycle, paid in ((0, date(2026, 9, 5)), (1, date(2026, 10, 12)), (2, date(2026, 11, 5))):
        payments.record_payment(
            student_id=bilal, cycle_number=cycle, paid_date=paid, amount=Decimal("300")
        )
    payments.record_payment(
        student_id=amina, cycle_number=0, paid_date=date(2026, 9, 5), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=chaima, cycle_number=0, paid_date=date(2026, 9, 5), amount=Decimal("300")
    )
    EnrollmentService(session).leave(chaima, leave_date=date(2026, 10, 20))
    return {"amina": amina, "bilal": bilal, "chaima": chaima}


@pytest.fixture
def school(cli_db: str) -> dict[str, int]:
    with _teacher() as session:
        return _school(session)


_AS_OF = ["--as-of", "2026-11-21"]


# --------------------------------------------------------------------------- #
# students
# --------------------------------------------------------------------------- #


def test_list_puts_who_owes_most_first(school: dict[str, int]) -> None:
    result = runner.invoke(app, ["students", "list", *_AS_OF])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    first = next(i for i, line in enumerate(lines) if "Amina" in line)
    assert first < next(i for i, line in enumerate(lines) if "Bilal" in line)
    assert "600 DH (2 mo)" in result.output
    assert "2BAC — Groupe A" in result.output


def test_list_can_show_only_who_owes(school: dict[str, int]) -> None:
    result = runner.invoke(app, ["students", "list", "--owing", *_AS_OF])
    assert "Amina" in result.output
    assert "Bilal" not in result.output


def test_list_marks_who_left_and_can_search(school: dict[str, int]) -> None:
    everyone = runner.invoke(app, ["students", "list", *_AS_OF])
    assert "Chaima Idrissi (left)" in everyone.output
    found = runner.invoke(app, ["students", "list", "--search", "taz", *_AS_OF])
    assert "Bilal" in found.output and "Amina" not in found.output


def test_show_gives_the_facts_and_every_month(school: dict[str, int]) -> None:
    result = runner.invoke(app, ["students", "show", str(school["amina"]), *_AS_OF])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Amina Benali" in out and "Paie le samedi" in out
    assert "600 DH (2 months)" in out
    for month in ("2026-09", "2026-10", "2026-11"):
        assert month in out
    assert out.count("unpaid") == 2


def test_show_finds_a_student_by_name(school: dict[str, int]) -> None:
    result = runner.invoke(app, ["students", "show", "bilal", *_AS_OF])
    assert result.exit_code == 0, result.output
    assert "Bilal Tazi" in result.output
    assert "late" in result.output  # October, paid on the 12th


def test_show_asks_for_more_when_a_name_matches_several(school: dict[str, int]) -> None:
    result = runner.invoke(app, ["students", "show", "a"])
    assert result.exit_code == 1
    assert "matches 3 students" in result.output


def test_show_refuses_an_unknown_student(cli_db: str) -> None:
    assert runner.invoke(app, ["students", "show", "999"]).exit_code == 1
    nobody = runner.invoke(app, ["students", "show", "nobody"])
    assert nobody.exit_code == 1
    assert "No student matches" in nobody.output


def test_show_marks_months_away_as_away(cli_db: str) -> None:
    with _teacher() as session:
        sid = (
            StudentService(session)
            .enroll(first_name="Dina", phone=None, join_date=date(2026, 9, 5))
            .id
        )
        EnrollmentService(session).leave(sid, leave_date=date(2026, 9, 30))
        EnrollmentService(session).return_(sid, entry_date=date(2026, 11, 1))
    result = runner.invoke(app, ["students", "show", "dina", *_AS_OF])
    assert "away" in result.output


def test_delete_needs_the_full_name_typed(school: dict[str, int]) -> None:
    wrong = runner.invoke(app, ["students", "delete", "amina"], input="Amina\n")
    assert wrong.exit_code == 1
    assert "nothing was deleted" in wrong.output
    assert runner.invoke(app, ["students", "show", "amina"]).exit_code == 0

    right = runner.invoke(app, ["students", "delete", "amina"], input="amina benali\n")
    assert right.exit_code == 0, right.output
    assert runner.invoke(app, ["students", "show", "amina"]).exit_code == 1


# --------------------------------------------------------------------------- #
# debts and the school's share
# --------------------------------------------------------------------------- #


def test_debts_lists_who_left_owing(school: dict[str, int]) -> None:
    result = runner.invoke(app, ["debts", "list"])
    assert result.exit_code == 0, result.output
    assert "Chaima Idrissi" in result.output and "Amina" not in result.output
    assert "Total owed: 300 DH" in result.output


def test_share_lists_each_month_and_what_was_handed_over(
    school: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "school_share_percent", Decimal("25"))
    with _teacher() as session:
        SchoolShareHandoverService(session).mark(
            2026, 9, handed_on=date(2026, 10, 3), share_percent=Decimal("25"),
            today=date(2026, 11, 21),
        )  # fmt: skip
    result = runner.invoke(app, ["share", "list", *_AS_OF])
    assert result.exit_code == 0, result.output
    september = next(line for line in result.output.splitlines() if "2026-09" in line)
    assert "900 DH" in september and "225 DH" in september and "2026-10-03" in september
    october = next(line for line in result.output.splitlines() if "2026-10" in line)
    assert "due" in october


def test_share_says_so_when_there_is_nothing(cli_db: str) -> None:
    result = runner.invoke(app, ["share", "list"])
    assert result.exit_code == 0
    assert "No share to show" in result.output


# --------------------------------------------------------------------------- #
# db and openapi
# --------------------------------------------------------------------------- #


def test_db_reset_is_refused_without_the_switch(cli_db: str) -> None:
    result = runner.invoke(app, ["db", "reset", "--yes"])
    assert result.exit_code == 1
    assert "ALLOW_DB_RESET" in result.output


def test_db_reset_with_the_switch_leaves_a_clean_central_database(
    cli_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOW_DB_RESET", "1")
    result = runner.invoke(app, ["db", "reset", "--yes"])
    assert result.exit_code == 0, result.output
    accounts = runner.invoke(app, ["users", "list"])
    assert "No accounts yet" in accounts.output


def test_db_migrate_brings_every_database_up(cli_db: str) -> None:
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0, result.output
    assert "1 teacher(s)" in result.output


def test_openapi_prints_the_schema_as_plain_json(cli_db: str) -> None:
    result = runner.invoke(app, ["openapi"])
    assert result.exit_code == 0
    schema = json.loads(result.output)
    assert "/api/v1/students" in schema["paths"]


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("amount", "shown"),
    [("1690", "1,690 DH"), ("199.50", "199.50 DH"), ("300.00", "300 DH"), (None, "—")],
)
def test_money_reads_like_the_app(amount: str | None, shown: str) -> None:
    assert money(Decimal(amount) if amount is not None else None) == shown


def test_dates_must_be_real(cli_db: str) -> None:
    result = runner.invoke(app, ["students", "list", "--as-of", "2026-13-01"])
    assert result.exit_code != 0
    assert "Invalid date" in result.output


def test_as_of_defaults_to_today(cli_db: str) -> None:
    result = runner.invoke(app, ["students", "list"])
    assert f"as of {date.today()}" in result.output
