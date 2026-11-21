"""What every command shares: the app, the teacher it works on, sessions, errors and formatting."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from app.core.db import get_sessionmaker
from app.core.i18n import translate
from app.core.provisioning import ensure_tenant
from app.models import SchoolClass, Student
from app.services.auth_service import AuthService
from app.services.exceptions import DomainError
from app.services.student_service import StudentService

app = typer.Typer(
    help="Ardoise admin: accounts, database operations, and read-only lookups. "
    "Everything else is done in the app.",
    no_args_is_help=True,
)
console = Console()

# Which teacher's database the student/debt/share commands read. Set by the global `--user`
# option (or ARDOISE_USER); `None` means not chosen, which those commands refuse rather than
# guess: reading or deleting in the wrong teacher's file is not a mistake you notice quickly.
_selected_user: str | None = None


@app.callback()
def main(
    user: str | None = typer.Option(
        None,
        "--user",
        "-u",
        envvar="ARDOISE_USER",
        help="Which teacher's data to look at (their username). Not needed for `users` or `db`.",
    ),
) -> None:
    """Ardoise admin."""
    global _selected_user
    _selected_user = user


def abort(message: str) -> NoReturn:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=1)


@contextmanager
def domain_errors() -> Iterator[None]:
    """Turn a refusal from a service into a one-line message and exit code 1, not a traceback.
    The CLI speaks English: it's the developer's tool."""
    try:
        yield
    except DomainError as exc:
        abort(translate(f"error.{exc.code}", "en", **exc.params))


@contextmanager
def central_session() -> Iterator[Session]:
    """A session on the central database: accounts and sessions."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def teacher_session() -> Iterator[Session]:
    """A session on the selected teacher's own database (see `--user`)."""
    if _selected_user is None:
        abort(
            "Which teacher? Pass --user <username> (or set ARDOISE_USER). "
            "Run `ardoise users list` to see the accounts."
        )
    with central_session() as central, domain_errors():
        user = AuthService(central).get_user(_selected_user)
        # ensure_tenant, as the API's get_db does: SQLite would open a missing file as an empty
        # database, and every command would fail on "no such table".
        url = ensure_tenant(user.id)
    session = get_sessionmaker(url)()
    try:
        yield session
    finally:
        session.close()


def parse_date(value: str | None) -> date:
    """`YYYY-MM-DD`, or today when not given."""
    if value is None:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid date '{value}', expected YYYY-MM-DD") from exc


def money(amount: Decimal | None) -> str:
    """ "1,690 DH", "199.50 DH"; cents only when there are some, as the app shows money."""
    if amount is None:
        return "—"
    cents = amount.quantize(Decimal("0.01"))
    shown = f"{cents:,.0f}" if cents == cents.to_integral_value() else f"{cents:,.2f}"
    return f"{shown} DH"


def class_label(school_class: SchoolClass | None) -> str:
    return "—" if school_class is None else f"{school_class.level.value} — {school_class.name}"


def find_student(session: Session, ref: str) -> Student:
    """A student by id, or by a piece of their name ("amina", "benali"), as long as it names one."""
    students = StudentService(session)
    if ref.isdigit():
        with domain_errors():
            return students.get(int(ref))
    needle = ref.casefold()
    matches = [s for s in students.list() if needle in s.full_name.casefold()]
    if not matches:
        abort(f"No student matches '{ref}'.")
    if len(matches) > 1:
        names = ", ".join(f"{s.full_name} ({s.id})" for s in matches)
        abort(f"'{ref}' matches {len(matches)} students: {names}. Use the id or more of the name.")
    return matches[0]


def table(title: str, *columns: str) -> Table:
    """A Rich table; a column named with a leading ">" is right-aligned (numbers, money)."""
    result = Table(title=title)
    for column in columns:
        if column.startswith(">"):
            result.add_column(column[1:], justify="right")
        else:
            result.add_column(column)
    return result
