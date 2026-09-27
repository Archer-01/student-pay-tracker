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
from app.core.provisioning import provision_tenant
from app.core.settings import settings
from app.models import User

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A migrated central database plus one teacher, selected via ARDOISE_USER.

    Domain commands operate on a teacher's own database and refuse to guess which one, so every
    invocation below would otherwise have to pass `--user`. Setting the environment variable once
    here keeps ~100 call sites unchanged and matches how the CLI is actually used on a host.

    The account row is inserted directly rather than through `AuthService.create_user`: that hashes
    with argon2id (~25ms by design), and paying it once per test in this file is ~2s of pure waste
    for a password nothing here ever verifies.
    """
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    db_module.clear_engine_cache()
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")  # env.py reads the patched url

    with db_module.get_sessionmaker()() as session:
        user = User(
            username="cli",
            display_name="CLI",
            password_hash="unused-in-these-tests",
            is_active=True,
        )
        session.add(user)
        session.commit()
        provision_tenant(user.id)

    monkeypatch.setenv("ARDOISE_USER", "cli")
    yield url
    db_module.clear_engine_cache()


def _add_student(name: str = "Amina", join: str = "2023-03-05") -> None:
    """A student with no pack and no agreed price — priced only once put on a pack."""
    result = runner.invoke(app, ["students", "add", "--first-name", name, "--join-date", join])
    assert result.exit_code == 0, result.output


def test_students_add_and_show(cli_db: str) -> None:
    _add_student()
    show = runner.invoke(app, ["students", "show", "1"])
    assert show.exit_code == 0, show.output
    assert "Amina" in show.output


def test_students_delete(cli_db: str) -> None:
    _add_student()
    result = runner.invoke(app, ["students", "delete", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, ["students", "show", "1"]).exit_code != 0


def test_students_delete_requires_confirmation(cli_db: str) -> None:
    _add_student()
    # Decline the confirmation prompt -> aborts, student survives.
    result = runner.invoke(app, ["students", "delete", "1"], input="n\n")
    assert result.exit_code != 0
    assert runner.invoke(app, ["students", "show", "1"]).exit_code == 0


def test_students_delete_cascades(cli_db: str) -> None:
    _add_student()
    paid = runner.invoke(
        app, ["payments", "record", "1", "--date", "2023-04-10", "--amount", "300", "--cycle", "1"]
    )
    assert paid.exit_code == 0, paid.output
    result = runner.invoke(app, ["students", "delete", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, ["students", "show", "1"]).exit_code != 0


def test_students_delete_unknown_errors(cli_db: str) -> None:
    result = runner.invoke(app, ["students", "delete", "999", "--yes"])
    assert result.exit_code != 0
    assert "999" in result.output


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


def test_db_seed_populates_data(cli_db: str) -> None:
    result = runner.invoke(app, ["db", "seed"])
    assert result.exit_code == 0, result.output
    listed = runner.invoke(app, ["students", "list"])
    assert "Amina Benali" in listed.output


def test_db_seed_refuses_when_not_empty_without_force(cli_db: str) -> None:
    assert runner.invoke(app, ["db", "seed"]).exit_code == 0
    again = runner.invoke(app, ["db", "seed"])
    assert again.exit_code != 0
    assert "--force" in again.output
    # --force seeds a second time.
    assert runner.invoke(app, ["db", "seed", "--force"]).exit_code == 0


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


# --------------------------------------------------------------------------- #
# classes
# --------------------------------------------------------------------------- #


def _add_class(level: str = "2BAC", name: str = "Groupe A") -> None:
    result = runner.invoke(app, ["classes", "add", "--level", level, "--name", name])
    assert result.exit_code == 0, result.output


def test_classes_add_and_list(cli_db: str) -> None:
    _add_class()
    listed = runner.invoke(app, ["classes", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Groupe A" in listed.output
    assert "2BAC" in listed.output


def test_classes_list_is_in_school_order(cli_db: str) -> None:
    _add_class("2BAC", "Z")
    _add_class("1AC", "A")
    listed = runner.invoke(app, ["classes", "list"])
    assert listed.output.index("1AC") < listed.output.index("2BAC")


def test_classes_add_duplicate_fails(cli_db: str) -> None:
    _add_class()
    dup = runner.invoke(app, ["classes", "add", "--level", "2BAC", "--name", "Groupe A"])
    assert dup.exit_code == 1
    assert "already exists" in dup.output


def test_classes_add_invalid_level_fails(cli_db: str) -> None:
    bad = runner.invoke(app, ["classes", "add", "--level", "6BAC", "--first-name", "X"])
    assert bad.exit_code != 0


def test_classes_show_lists_the_roster(cli_db: str) -> None:
    _add_class()
    _add_student()
    assert runner.invoke(app, ["students", "assign-class", "1", "--class-id", "1"]).exit_code == 0
    shown = runner.invoke(app, ["classes", "show", "1"])
    assert shown.exit_code == 0, shown.output
    assert "Amina" in shown.output


def test_classes_rename(cli_db: str) -> None:
    _add_class()
    renamed = runner.invoke(app, ["classes", "rename", "1", "--name", "Groupe Z"])
    assert renamed.exit_code == 0, renamed.output
    assert "Groupe Z" in runner.invoke(app, ["classes", "list"]).output


def test_classes_delete_empty(cli_db: str) -> None:
    _add_class()
    deleted = runner.invoke(app, ["classes", "delete", "1", "--yes"])
    assert deleted.exit_code == 0, deleted.output
    assert "Groupe A" not in runner.invoke(app, ["classes", "list"]).output


def test_classes_delete_non_empty_fails(cli_db: str) -> None:
    _add_class()
    _add_student()
    runner.invoke(app, ["students", "assign-class", "1", "--class-id", "1"])
    failed = runner.invoke(app, ["classes", "delete", "1", "--yes"])
    assert failed.exit_code == 1
    assert "unassign" in failed.output.lower()


def test_students_add_with_class(cli_db: str) -> None:
    _add_class()
    result = runner.invoke(
        app,
        ["students", "add", "--first-name", "Amina",
         "--join-date", "2023-03-05", "--class-id", "1"],
    )
    assert result.exit_code == 0, result.output
    assert "Amina" in runner.invoke(app, ["classes", "show", "1"]).output


def test_students_add_with_unknown_class_fails(cli_db: str) -> None:
    result = runner.invoke(
        app,
        ["students", "add", "--first-name", "X", "--join-date", "2023-03-05", "--class-id", "99"],
    )
    assert result.exit_code == 1
    assert "No class with id 99" in result.output


def test_students_unassign_class(cli_db: str) -> None:
    _add_class()
    _add_student()
    runner.invoke(app, ["students", "assign-class", "1", "--class-id", "1"])
    unassigned = runner.invoke(app, ["students", "assign-class", "1", "--none"])
    assert unassigned.exit_code == 0, unassigned.output
    assert "Amina" not in runner.invoke(app, ["classes", "show", "1"]).output


def test_students_assign_class_requires_exactly_one_target(cli_db: str) -> None:
    _add_student()
    assert runner.invoke(app, ["students", "assign-class", "1"]).exit_code != 0
    assert runner.invoke(
        app, ["students", "assign-class", "1", "--class-id", "1", "--none"]
    ).exit_code != 0


def test_students_list_shows_class(cli_db: str) -> None:
    _add_class()
    _add_student()
    runner.invoke(app, ["students", "assign-class", "1", "--class-id", "1"])
    listed = runner.invoke(app, ["students", "list"])
    assert "2BAC — Groupe A" in listed.output


# --------------------------------------------------------------------------- #
# packs
# --------------------------------------------------------------------------- #


def _add_pack(name: str = "Maths seul", level: str = "2BAC", price: str = "150") -> None:
    result = runner.invoke(
        app,
        ["packs", "add", "--name", name, "--level", level, "--price", price,
         "--subject", "Maths"],
    )
    assert result.exit_code == 0, result.output


def test_packs_add_and_list(cli_db: str) -> None:
    _add_pack()
    listed = runner.invoke(app, ["packs", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Maths seul" in listed.output
    assert "2BAC" in listed.output


def test_packs_add_duplicate_fails(cli_db: str) -> None:
    _add_pack()
    dup = runner.invoke(
        app,
        ["packs", "add", "--name", "Maths seul", "--level", "2BAC", "--price", "9",
         "--subject", "Maths"],
    )
    assert dup.exit_code == 1
    assert "already exists" in dup.output


def test_packs_grid_shows_offered_and_missing_levels(cli_db: str) -> None:
    _add_pack(level="2BAC", price="150")
    grid = runner.invoke(app, ["packs", "grid"])
    assert grid.exit_code == 0, grid.output
    assert "Maths seul" in grid.output
    assert "150" in grid.output
    assert "—" in grid.output  # levels the offering isn't sold at


def test_packs_deactivate(cli_db: str) -> None:
    _add_pack()
    assert runner.invoke(app, ["packs", "deactivate", "1"]).exit_code == 0
    assert "no" in runner.invoke(app, ["packs", "list"]).output


def test_packs_delete_unused(cli_db: str) -> None:
    _add_pack()
    assert runner.invoke(app, ["packs", "delete", "1", "--yes"]).exit_code == 0


def test_set_pack_and_price(cli_db: str) -> None:
    _add_pack(price="150")
    _add_student()
    result = runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    assert result.exit_code == 0, result.output
    assert "Maths seul" in result.output
    assert "150" in result.output


def test_set_pack_with_an_agreed_price(cli_db: str) -> None:
    _add_pack(price="150")
    _add_student()
    result = runner.invoke(
        app,
        ["students", "set-pack", "1", "--pack-id", "1", "--price", "90", "--price-note", "remise"],
    )
    assert result.exit_code == 0, result.output
    assert "90" in result.output


def test_clear_price_returns_to_the_pack_price(cli_db: str) -> None:
    _add_pack(price="150")
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1", "--price", "90"])
    cleared = runner.invoke(
        app, ["students", "set-pack", "1", "--pack-id", "1", "--clear-price"]
    )
    assert cleared.exit_code == 0, cleared.output
    assert "150" in cleared.output


def test_set_pack_warns_on_a_level_mismatch(cli_db: str) -> None:
    _add_pack(level="2BAC")
    _add_class("1AC", "Groupe A")
    _add_student()
    runner.invoke(app, ["students", "assign-class", "1", "--class-id", "1"])
    result = runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    assert result.exit_code == 0, result.output  # advisory, never a refusal
    assert "warning" in result.output.lower()


def test_set_unknown_pack_fails(cli_db: str) -> None:
    _add_student()
    result = runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "99"])
    assert result.exit_code == 1
    assert "No pack with id 99" in result.output


def test_set_pack_requires_exactly_one_target(cli_db: str) -> None:
    _add_student()
    assert runner.invoke(app, ["students", "set-pack", "1"]).exit_code != 0
    assert runner.invoke(
        app, ["students", "set-pack", "1", "--pack-id", "1", "--none"]
    ).exit_code != 0


def test_remove_a_student_from_their_pack(cli_db: str) -> None:
    _add_pack()
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    removed = runner.invoke(app, ["students", "set-pack", "1", "--none"])
    assert removed.exit_code == 0, removed.output
    assert "no pack" in removed.output


def test_packs_delete_in_use_fails(cli_db: str) -> None:
    _add_pack()
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    result = runner.invoke(app, ["packs", "delete", "1", "--yes"])
    assert result.exit_code == 1
    assert "deactivate" in result.output.lower()


def test_students_list_marks_an_agreed_price(cli_db: str) -> None:
    _add_pack(price="150")
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    plain = runner.invoke(app, ["students", "list"])
    assert "150.00" in plain.output and "150.00*" not in plain.output

    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1", "--price", "90"])
    starred = runner.invoke(app, ["students", "list"])
    assert "90.00*" in starred.output


def test_packs_edit_offering_renames_every_level(cli_db: str) -> None:
    _add_pack(name="Maths seul", level="2BAC", price="150")
    _add_pack(name="Maths seul", level="1AC", price="100")
    result = runner.invoke(app, ["packs", "edit-offering", "Maths seul", "--rename", "Maths"])
    assert result.exit_code == 0, result.output
    assert "2 level(s)" in result.output
    listed = runner.invoke(app, ["packs", "list"]).output
    assert "Maths seul" not in listed


def test_packs_edit_offering_sets_subjects_everywhere(cli_db: str) -> None:
    _add_pack(name="Maths seul", level="2BAC")
    _add_pack(name="Maths seul", level="1AC")
    result = runner.invoke(
        app,
        ["packs", "edit-offering", "Maths seul", "--subject", "Maths", "--subject", "Physique"],
    )
    assert result.exit_code == 0, result.output
    assert "Maths, Physique" in result.output


def test_packs_edit_offering_requires_something_to_change(cli_db: str) -> None:
    _add_pack()
    assert runner.invoke(app, ["packs", "edit-offering", "Maths seul"]).exit_code != 0


def test_packs_edit_unknown_offering_fails(cli_db: str) -> None:
    result = runner.invoke(app, ["packs", "edit-offering", "Nope", "--rename", "X"])
    assert result.exit_code == 1
    assert "No pack offering named" in result.output


# --------------------------------------------------------------------------- #
# leave / return
# --------------------------------------------------------------------------- #


def test_students_leave_and_return(cli_db: str) -> None:
    _add_student()
    left = runner.invoke(app, ["students", "leave", "1", "--on", "2023-06-30", "--reason", "moved"])
    assert left.exit_code == 0, left.output
    assert "2023-06-30" in left.output
    back = runner.invoke(app, ["students", "return", "1", "--on", "2023-10-01"])
    assert back.exit_code == 0, back.output
    periods = runner.invoke(app, ["students", "periods", "1"])
    assert "2023-06-30" in periods.output
    assert "attending" in periods.output


def test_students_leave_twice_fails(cli_db: str) -> None:
    _add_student()
    runner.invoke(app, ["students", "leave", "1", "--on", "2023-06-30"])
    again = runner.invoke(app, ["students", "leave", "1", "--on", "2023-07-30"])
    assert again.exit_code == 1
    assert "already left" in again.output


def test_students_return_without_leaving_fails(cli_db: str) -> None:
    _add_student()
    result = runner.invoke(app, ["students", "return", "1", "--on", "2023-10-01"])
    assert result.exit_code == 1
    assert "already attending" in result.output


def test_students_show_marks_away_months(cli_db: str) -> None:
    _add_student()
    runner.invoke(app, ["students", "leave", "1", "--on", "2023-05-31"])
    runner.invoke(app, ["students", "return", "1", "--on", "2023-09-01"])
    shown = runner.invoke(app, ["students", "show", "1", "--as-of", "2023-10-31"])
    assert shown.exit_code == 0, shown.output
    assert "away" in shown.output


# --------------------------------------------------------------------------- #
# debts
# --------------------------------------------------------------------------- #


def test_debts_list_shows_leavers_who_owe(cli_db: str) -> None:
    _add_pack(price="300")
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    runner.invoke(app, ["students", "leave", "1", "--on", "2023-06-30"])
    listed = runner.invoke(app, ["debts", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Amina" in listed.output
    assert "Total owed" in listed.output


def test_debts_list_excludes_students_still_here(cli_db: str) -> None:
    _add_pack(price="300")
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    assert "Amina" not in runner.invoke(app, ["debts", "list"]).output


def test_debts_write_off_clears_the_list(cli_db: str) -> None:
    _add_pack(price="300")
    _add_student()
    runner.invoke(app, ["students", "set-pack", "1", "--pack-id", "1"])
    runner.invoke(app, ["students", "leave", "1", "--on", "2023-06-30"])
    result = runner.invoke(app, ["debts", "write-off", "1", "--reason", "forgiven"])
    assert result.exit_code == 0, result.output
    assert "Wrote off" in result.output
    assert "Amina" not in runner.invoke(app, ["debts", "list"]).output


def test_debts_write_off_with_nothing_owed_fails(cli_db: str) -> None:
    _add_student()
    result = runner.invoke(app, ["debts", "write-off", "1", "--reason", "x"])
    assert result.exit_code == 1
    assert "no outstanding balance" in result.output
