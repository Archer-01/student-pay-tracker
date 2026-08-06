"""Command-line admin tool (`uv run tracker ...`).

Thin wiring over the service layer — no domain logic lives here. The CLI and the (future) API
both call the same services, so they produce identical results.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from app.core.db import get_engine, get_sessionmaker
from app.core.i18n import translate
from app.core.settings import settings
from app.models import StudentStatus
from app.services.exceptions import DomainError
from app.services.ledger_service import LedgerService
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

app = typer.Typer(help="Student payment tracker admin CLI.", no_args_is_help=True)
students_app = typer.Typer(help="Manage students.", no_args_is_help=True)
payments_app = typer.Typer(help="Record payments.", no_args_is_help=True)
overrides_app = typer.Typer(help="Manage anchor overrides.", no_args_is_help=True)
db_app = typer.Typer(help="Database maintenance (dev only).", no_args_is_help=True)
app.add_typer(students_app, name="students")
app.add_typer(payments_app, name="payments")
app.add_typer(overrides_app, name="overrides")
app.add_typer(db_app, name="db")

console = Console()


@contextmanager
def _session() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _abort(message: str) -> NoReturn:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=1)


def _render_error(exc: Exception) -> str:
    """Render an error message for the CLI (always English — it's the dev/admin tool)."""
    if isinstance(exc, DomainError):
        return translate(f"error.{exc.code}", "en", **exc.params)
    return str(exc)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid date '{value}', expected YYYY-MM-DD") from exc


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise typer.BadParameter(f"Invalid amount '{value}'") from exc


def _parse_month(value: str) -> tuple[int, int]:
    parts = value.split("-")
    try:
        if len(parts) != 2:
            raise ValueError
        year, month = int(parts[0]), int(parts[1])
        date(year, month, 1)  # validate the month is real
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid month '{value}', expected YYYY-MM") from exc
    return year, month


def _as_of(value: str | None) -> date:
    return _parse_date(value) if value else date.today()


# --------------------------------------------------------------------------- #
# students
# --------------------------------------------------------------------------- #


@students_app.command("add")
def students_add(
    name: str = typer.Option(..., "--name"),
    join_date: str = typer.Option(..., "--join-date", help="YYYY-MM-DD"),
    fee: str = typer.Option(..., "--fee"),
    phone: str | None = typer.Option(None, "--phone"),
    status: StudentStatus = typer.Option(StudentStatus.ACTIVE, "--status"),
) -> None:
    """Enroll a new student."""
    with _session() as session:
        student = StudentService(session).enroll(
            name=name,
            phone=phone,
            join_date=_parse_date(join_date),
            fee=_parse_decimal(fee),
            status=status,
        )
        console.print(f"Enrolled [bold]{student.name}[/bold] with id [bold]{student.id}[/bold].")


@students_app.command("list")
def students_list(
    sort_by_drift: bool = typer.Option(False, "--sort-by-drift"),
    status: StudentStatus | None = typer.Option(None, "--status"),
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD (default: today)"),
) -> None:
    """List students, optionally sorted by cumulative drift (most first)."""
    as_of_date = _as_of(as_of)
    with _session() as session:
        ledger = LedgerService(session)
        rows = [
            (s, ledger.cumulative_drift(s.id, as_of_date))
            for s in StudentService(session).list(status=status)
        ]
        if sort_by_drift:
            rows.sort(key=lambda r: r[1], reverse=True)

        table = Table(title=f"Students (as of {as_of_date})")
        table.add_column("ID", justify="right")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Fee", justify="right")
        table.add_column("Drift", justify="right")
        for student, drift in rows:
            table.add_row(
                str(student.id), student.name, student.status.value, f"{student.fee}", str(drift)
            )
        console.print(table)


@students_app.command("show")
def students_show(
    student_id: int = typer.Argument(...),
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD (default: today)"),
) -> None:
    """Show a student's full ledger and cumulative drift."""
    as_of_date = _as_of(as_of)
    with _session() as session:
        try:
            student = StudentService(session).get(student_id)
            entries = LedgerService(session).get_ledger(student_id, as_of_date)
        except DomainError as exc:
            _abort(_render_error(exc))

        table = Table(title=f"{student.name} — ledger as of {as_of_date}")
        for col, justify in (
            ("Cycle", "right"),
            ("Due date", "left"),
            ("Paid date", "left"),
            ("Days late", "right"),
            ("Amount", "right"),
            ("Cumulative drift", "right"),
        ):
            table.add_column(col, justify=justify)  # type: ignore[arg-type]
        for e in entries:
            table.add_row(
                str(e.cycle_number),
                e.expected_due_date.isoformat(),
                e.paid_date.isoformat() if e.paid_date else "—",
                str(e.days_late) if e.days_late is not None else "—",
                f"{e.amount}" if e.amount is not None else "—",
                str(e.cumulative_drift),
            )
        console.print(table)
        total = entries[-1].cumulative_drift if entries else 0
        console.print(f"Cumulative drift: [bold]{total}[/bold]")


@students_app.command("delete")
def students_delete(
    student_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Delete a student and cascade to their payments and overrides (irreversible)."""
    if not yes:
        typer.confirm(
            f"This will permanently delete student {student_id} and all their "
            "payments and overrides. Continue?",
            abort=True,
        )
    with _session() as session:
        try:
            StudentService(session).delete(student_id)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"Deleted student [bold]{student_id}[/bold].")


# --------------------------------------------------------------------------- #
# payments
# --------------------------------------------------------------------------- #


@payments_app.command("record")
def payments_record(
    student_id: int = typer.Argument(...),
    date_: str = typer.Option(..., "--date", help="Paid date, YYYY-MM-DD"),
    amount: str = typer.Option(..., "--amount"),
    for_month: str | None = typer.Option(
        None, "--for-month", help="Which month it settles, YYYY-MM"
    ),
    cycle: int | None = typer.Option(None, "--cycle", help="Cycle index (from `students show`)"),
) -> None:
    """Record a payment. Provide exactly one of --for-month or --cycle."""
    if (for_month is None) == (cycle is None):
        raise typer.BadParameter("Provide exactly one of --for-month or --cycle.")

    paid = _parse_date(date_)
    amt = _parse_decimal(amount)
    with _session() as session:
        payments = PaymentService(session)
        try:
            if for_month is not None:
                year, month = _parse_month(for_month)
                cycle_number = payments.cycle_for_month(student_id, year, month)
            else:
                assert cycle is not None  # guaranteed by the exactly-one check
                cycle_number = cycle
            payment = payments.record_payment(
                student_id=student_id, cycle_number=cycle_number, paid_date=paid, amount=amt
            )
        except (DomainError, ValueError) as exc:
            _abort(_render_error(exc))

        console.print(
            f"Recorded payment for cycle [bold]{payment.cycle_number}[/bold] "
            f"(due {payment.expected_due_date}, {payment.days_late} days late)."
        )


# --------------------------------------------------------------------------- #
# overrides
# --------------------------------------------------------------------------- #


@overrides_app.command("create")
def overrides_create(
    student_id: int = typer.Argument(...),
    new_date: str = typer.Option(..., "--new-date", help="New due date, YYYY-MM-DD"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Record an anchor override (permanent re-anchor from its month)."""
    with _session() as session:
        try:
            override = OverrideService(session).create_override(
                student_id=student_id, new_due_date=_parse_date(new_date), reason=reason
            )
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(
            f"Recorded override (id [bold]{override.id}[/bold]): "
            f"due date -> {override.new_due_date}."
        )


# --------------------------------------------------------------------------- #
# db (dev only)
# --------------------------------------------------------------------------- #


@db_app.command("reset")
def db_reset(
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Drop and recreate all tables. Dev only — requires ALLOW_DB_RESET=1."""
    if os.environ.get("ALLOW_DB_RESET") != "1":
        _abort("Refusing to reset: set ALLOW_DB_RESET=1 to allow this (dev only).")
    if not yes:
        typer.confirm("This will DROP and recreate all tables. Continue?", abort=True)

    from alembic.config import Config

    from alembic import command

    get_engine.cache_clear()
    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    console.print(f"Database reset to a clean migrated state ({settings.database_url}).")


@db_app.command("seed")
def db_seed(
    force: bool = typer.Option(
        False, "--force", help="Seed even if the database already has students."
    ),
) -> None:
    """Populate the database with deterministic dummy data (dev only)."""
    from app.core.seed import seed_dummy_data

    with _session() as session:
        existing = StudentService(session).list()
        if existing and not force:
            _abort(
                f"Database already has {len(existing)} student(s); pass --force to seed anyway."
            )
        summary = seed_dummy_data(session)
    console.print(
        f"Seeded [bold]{summary.students}[/bold] students, "
        f"[bold]{summary.payments}[/bold] payments, "
        f"[bold]{summary.overrides}[/bold] overrides."
    )


@db_app.command("backup")
def db_backup(
    to: Path = typer.Option(Path("backups"), "--to", help="Destination directory."),
) -> None:
    """Write a timestamped backup of the SQLite database (cron-friendly)."""
    from app.core.backup import backup_database

    try:
        dest = backup_database(settings.database_url, to)
    except ValueError as exc:
        _abort(_render_error(exc))
    console.print(f"Backup written to [bold]{dest}[/bold].")


if __name__ == "__main__":
    app()
