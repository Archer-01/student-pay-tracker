"""Command-line admin tool (`uv run ardoise ...`).

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
from app.models import ClassLevel, Pack, StudentStatus
from app.services.class_service import ClassService
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import DomainError
from app.services.ledger_service import LedgerService
from app.services.override_service import OverrideService
from app.services.pack_service import PackService
from app.services.payment_service import PaymentService
from app.services.pricing_service import PricingService
from app.services.student_service import StudentService

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

app = typer.Typer(help="Ardoise admin CLI.", no_args_is_help=True)
students_app = typer.Typer(help="Manage students.", no_args_is_help=True)
payments_app = typer.Typer(help="Record payments.", no_args_is_help=True)
overrides_app = typer.Typer(help="Manage anchor overrides.", no_args_is_help=True)
classes_app = typer.Typer(help="Manage classes.", no_args_is_help=True)
packs_app = typer.Typer(help="Manage packs (the price list).", no_args_is_help=True)
debts_app = typer.Typer(help="Students who left owing money.", no_args_is_help=True)
db_app = typer.Typer(help="Database maintenance (dev only).", no_args_is_help=True)
app.add_typer(students_app, name="students")
app.add_typer(payments_app, name="payments")
app.add_typer(overrides_app, name="overrides")
app.add_typer(classes_app, name="classes")
app.add_typer(packs_app, name="packs")
app.add_typer(debts_app, name="debts")
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
    first_name: str = typer.Option(..., "--first-name"),
    last_name: str | None = typer.Option(None, "--last-name"),
    join_date: str = typer.Option(..., "--join-date", help="YYYY-MM-DD"),
    repeating: bool = typer.Option(False, "--repeating", help="Redoublant."),
    phone: str | None = typer.Option(None, "--phone"),
    status: StudentStatus = typer.Option(StudentStatus.ACTIVE, "--status"),
    class_id: int | None = typer.Option(None, "--class-id", help="Place them in this class."),
    pack_id: int | None = typer.Option(None, "--pack-id", help="The pack they're on."),
    price: str | None = typer.Option(
        None, "--price", help="Only if they don't pay the pack price."
    ),
    price_note: str | None = typer.Option(None, "--price-note", help="Why the agreed price."),
) -> None:
    """Enroll a new student."""
    with _session() as session:
        try:
            student = StudentService(session).enroll(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                is_repeating=repeating,
                join_date=_parse_date(join_date),
                status=status,
                class_id=class_id,
                pack_id=pack_id,
                custom_price=_parse_decimal(price) if price else None,
                price_note=price_note,
            )
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(
            f"Enrolled [bold]{student.full_name}[/bold] with id [bold]{student.id}[/bold]."
        )


@students_app.command("assign-class")
def students_assign_class(
    student_id: int = typer.Argument(...),
    class_id: int | None = typer.Option(None, "--class-id"),
    none: bool = typer.Option(False, "--none", help="Remove the student from their class."),
) -> None:
    """Move a student into a class, or out of one. Purely organisational — drift is untouched."""
    if (class_id is None) == (not none):
        raise typer.BadParameter("Provide exactly one of --class-id or --none.")
    with _session() as session:
        try:
            student = StudentService(session).update(
                student_id, class_id=None if none else class_id
            )
        except DomainError as exc:
            _abort(_render_error(exc))
        target = "no class" if student.class_id is None else f"class {student.class_id}"
        console.print(f"[bold]{student.full_name}[/bold] is now in {target}.")


@students_app.command("set-pack")
def students_set_pack(
    student_id: int = typer.Argument(...),
    pack_id: int | None = typer.Option(None, "--pack-id"),
    none: bool = typer.Option(False, "--none", help="Remove the student from their pack."),
    price: str | None = typer.Option(
        None, "--price", help="Agreed price, if they don't pay the pack price."
    ),
    clear_price: bool = typer.Option(
        False, "--clear-price", help="Drop the agreed price; they pay the pack price."
    ),
    price_note: str | None = typer.Option(None, "--price-note"),
) -> None:
    """Set a student's pack and/or what they pay."""
    if (pack_id is None) == (not none):
        raise typer.BadParameter("Provide exactly one of --pack-id or --none.")
    if price and clear_price:
        raise typer.BadParameter("Provide at most one of --price or --clear-price.")

    fields: dict[str, object] = {"pack_id": None if none else pack_id}
    if price:
        fields["custom_price"] = _parse_decimal(price)
    elif clear_price:
        fields["custom_price"] = None
    if price_note is not None:
        fields["price_note"] = price_note

    with _session() as session:
        pricing = PricingService(session)
        try:
            student = StudentService(session).update(student_id, **fields)  # type: ignore[arg-type]
        except DomainError as exc:
            _abort(_render_error(exc))
        label = (
            "no pack"
            if student.pack is None
            else f"{student.pack.name} · {student.pack.level.value}"
        )
        console.print(
            f"[bold]{student.full_name}[/bold] is on {label} "
            f"at [bold]{pricing.price_of(student)}[/bold]."
        )
        if student.pack is not None:
            mismatch = pricing.level_mismatch(student, student.pack)
            if mismatch:
                console.print(
                    f"  [yellow]warning:[/yellow] class is {mismatch[0].value} "
                    f"but the pack is for {mismatch[1].value}"
                )


@students_app.command("leave")
def students_leave(
    student_id: int = typer.Argument(...),
    on: str = typer.Option(..., "--on", help="Departure date, YYYY-MM-DD"),
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    """Record a departure. Months after it stop being owed; drift already accrued stays."""
    with _session() as session:
        try:
            period = EnrollmentService(session).leave(
                student_id, leave_date=_parse_date(on), reason=reason
            )
            student = StudentService(session).get(student_id)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"[bold]{student.full_name}[/bold] left on {period.leave_date}.")


@students_app.command("return")
def students_return(
    student_id: int = typer.Argument(...),
    on: str = typer.Option(..., "--on", help="Return date, YYYY-MM-DD"),
) -> None:
    """Record a return. The join date is never moved, so past drift and debt survive."""
    with _session() as session:
        try:
            period = EnrollmentService(session).return_(student_id, entry_date=_parse_date(on))
            student = StudentService(session).get(student_id)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"[bold]{student.full_name}[/bold] is back from {period.entry_date}.")


@students_app.command("periods")
def students_periods(student_id: int = typer.Argument(...)) -> None:
    """Show a student's attendance history, oldest first."""
    with _session() as session:
        try:
            history = EnrollmentService(session).history(student_id)
        except DomainError as exc:
            _abort(_render_error(exc))
        table = Table(title=f"Attendance — student {student_id}")
        table.add_column("From")
        table.add_column("Until")
        table.add_column("Reason")
        for period in history:
            table.add_row(
                period.entry_date.isoformat(),
                period.leave_date.isoformat() if period.leave_date else "— (attending)",
                period.leave_reason or "—",
            )
        console.print(table)


@students_app.command("list")
def students_list(
    sort_by_drift: bool = typer.Option(False, "--sort-by-drift"),
    status: StudentStatus | None = typer.Option(None, "--status"),
    query: str | None = typer.Option(None, "--search", help="Match first or last name."),
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD (default: today)"),
) -> None:
    """List students, optionally sorted by cumulative drift (most first)."""
    as_of_date = _as_of(as_of)
    with _session() as session:
        ledger = LedgerService(session)
        pricing = PricingService(session)
        rows = [
            (s, ledger.cumulative_drift(s.id, as_of_date))
            for s in StudentService(session).list(status=status, query=query)
        ]
        if sort_by_drift:
            rows.sort(key=lambda r: r[1], reverse=True)

        table = Table(title=f"Students (as of {as_of_date})")
        table.add_column("ID", justify="right")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Class")
        table.add_column("Pack")
        table.add_column("Price", justify="right")
        table.add_column("Drift", justify="right")
        for student, drift in rows:
            price = f"{pricing.price_of(student)}"
            table.add_row(
                str(student.id),
                # A dagger marks a repeating student (redoublant).
                f"{student.full_name}†" if student.is_repeating else student.full_name,
                student.status.value,
                _class_label(student.school_class),
                "—" if student.pack is None else student.pack.name,
                # A star marks an agreed price that differs from the pack's.
                f"{price}*" if student.custom_price is not None else price,
                str(drift),
            )
        console.print(table)
        console.print(
            "[dim]* = agreed price, differs from the pack price · † = repeating the year[/dim]"
        )


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

        table = Table(title=f"{student.full_name} — ledger as of {as_of_date}")
        for col, justify in (
            ("Cycle", "right"),
            ("Due date", "left"),
            ("Paid date", "left"),
            ("Days late", "right"),
            ("Amount", "right"),
            ("Cumulative drift", "right"),
            ("", "left"),
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
                "away" if e.suspended else "",
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
# classes
# --------------------------------------------------------------------------- #


def _class_label(school_class: object) -> str:
    """Render a class as "2BAC — Groupe A", or an em dash when unassigned."""
    if school_class is None:
        return "—"
    return f"{school_class.level.value} — {school_class.name}"  # type: ignore[attr-defined]


@classes_app.command("add")
def classes_add(
    level: ClassLevel = typer.Option(..., "--level"),
    name: str = typer.Option(..., "--name"),
) -> None:
    """Create a class."""
    with _session() as session:
        try:
            created = ClassService(session).create(level=level, name=name)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(
            f"Created class [bold]{_class_label(created)}[/bold] with id [bold]{created.id}[/bold]."
        )


@classes_app.command("list")
def classes_list(
    level: ClassLevel | None = typer.Option(None, "--level"),
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD (default: today)"),
) -> None:
    """List classes in school order, with student counts and class-wide drift."""
    as_of_date = _as_of(as_of)
    with _session() as session:
        service = ClassService(session)
        table = Table(title=f"Classes (as of {as_of_date})")
        table.add_column("ID", justify="right")
        table.add_column("Level")
        table.add_column("Name")
        table.add_column("Students", justify="right")
        table.add_column("Drift", justify="right")
        for school_class in service.list(level=level):
            rows = service.roster(school_class.id, as_of_date)
            table.add_row(
                str(school_class.id),
                school_class.level.value,
                school_class.name,
                str(len(rows)),
                str(sum(r.cumulative_drift for r in rows)),
            )
        console.print(table)


@classes_app.command("show")
def classes_show(
    class_id: int = typer.Argument(...),
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD (default: today)"),
) -> None:
    """Show a class's roster with each student's drift and arrears."""
    as_of_date = _as_of(as_of)
    with _session() as session:
        service = ClassService(session)
        try:
            school_class = service.get(class_id)
            rows = service.roster(class_id, as_of_date)
        except DomainError as exc:
            _abort(_render_error(exc))

        table = Table(title=f"{_class_label(school_class)} — roster as of {as_of_date}")
        table.add_column("ID", justify="right")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Price", justify="right")
        table.add_column("Drift", justify="right")
        table.add_column("Months overdue", justify="right")
        table.add_column("Owed", justify="right")
        for row in rows:
            table.add_row(
                str(row.student.id),
                row.student.full_name,
                row.student.status.value,
                f"{row.monthly_price}",
                str(row.cumulative_drift),
                str(row.months_overdue),
                f"{row.amount_owed}",
            )
        console.print(table)


@classes_app.command("rename")
def classes_rename(
    class_id: int = typer.Argument(...),
    name: str | None = typer.Option(None, "--name"),
    level: ClassLevel | None = typer.Option(None, "--level"),
) -> None:
    """Rename a class and/or move it to a different level."""
    if name is None and level is None:
        raise typer.BadParameter("Provide --name and/or --level.")
    fields: dict[str, object] = {}
    if name is not None:
        fields["name"] = name
    if level is not None:
        fields["level"] = level
    with _session() as session:
        try:
            updated = ClassService(session).update(class_id, **fields)  # type: ignore[arg-type]
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"Class {class_id} is now [bold]{_class_label(updated)}[/bold].")


@classes_app.command("delete")
def classes_delete(
    class_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Delete an empty class. A class that still has students is refused."""
    if not yes:
        typer.confirm(f"Delete class {class_id}?", abort=True)
    with _session() as session:
        try:
            ClassService(session).delete(class_id)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"Deleted class [bold]{class_id}[/bold].")


# --------------------------------------------------------------------------- #
# packs
# --------------------------------------------------------------------------- #


@packs_app.command("add")
def packs_add(
    name: str = typer.Option(..., "--name", help='Offering, e.g. "Maths seul"'),
    level: ClassLevel = typer.Option(..., "--level"),
    price: str = typer.Option(..., "--price"),
    subject: list[str] = typer.Option(..., "--subject", help="Repeatable."),
) -> None:
    """Create one pack (one offering at one level)."""
    with _session() as session:
        try:
            pack = PackService(session).create(
                name=name, level=level, price=_parse_decimal(price), subjects=list(subject)
            )
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(
            f"Created pack [bold]{pack.name} · {pack.level.value}[/bold] "
            f"at [bold]{pack.price}[/bold] (id {pack.id})."
        )


@packs_app.command("grid")
def packs_grid() -> None:
    """Print the offerings x levels price matrix — the fastest way to check a price round."""
    with _session() as session:
        service = PackService(session)
        packs = service.list()
        levels = list(ClassLevel)
        by_offering: dict[str, dict[ClassLevel, Pack]] = {}
        for pack in packs:
            by_offering.setdefault(pack.name, {})[pack.level] = pack

        table = Table(title="Pack prices")
        table.add_column("Offering")
        for level in levels:
            table.add_column(level.value, justify="right")
        for name, variants in by_offering.items():
            cells: list[str] = []
            for level in levels:
                variant = variants.get(level)
                if variant is None:
                    cells.append("—")
                else:
                    price = f"{variant.price}"
                    cells.append(price if variant.is_active else f"({price})")
            table.add_row(name, *cells)
        console.print(table)
        console.print("[dim]( ) = inactive · — = not offered at that level[/dim]")


@packs_app.command("list")
def packs_list(
    level: ClassLevel | None = typer.Option(None, "--level"),
) -> None:
    """List packs with their subjects and how many assignments reference them."""
    with _session() as session:
        service = PackService(session)
        table = Table(title="Packs")
        for col, justify in (
            ("ID", "right"),
            ("Offering", "left"),
            ("Level", "left"),
            ("Price", "right"),
            ("Subjects", "left"),
            ("Active", "left"),
            ("Students", "right"),
        ):
            table.add_column(col, justify=justify)  # type: ignore[arg-type]
        for pack in service.list(level=level):
            table.add_row(
                str(pack.id),
                pack.name,
                pack.level.value,
                f"{pack.price}",
                ", ".join(s.name for s in pack.subjects),
                "yes" if pack.is_active else "no",
                str(service.student_count(pack.id)),
            )
        console.print(table)


@packs_app.command("edit-offering")
def packs_edit_offering(
    name: str = typer.Argument(..., help='The offering, e.g. "Maths seul"'),
    rename: str | None = typer.Option(None, "--rename", help="New name for the offering."),
    subject: list[str] | None = typer.Option(
        None, "--subject", help="Replace the subject list. Repeatable."
    ),
) -> None:
    """Rename an offering and/or set its subjects, across every level at once.

    Editing per-level is deliberately impossible: an offering's variants must keep the same name
    and subjects, and only their prices differ.
    """
    if rename is None and not subject:
        raise typer.BadParameter("Provide --rename and/or at least one --subject.")
    fields: dict[str, object] = {}
    if rename is not None:
        fields["new_name"] = rename
    if subject:
        fields["subjects"] = list(subject)

    with _session() as session:
        try:
            variants = PackService(session).update_offering(name, **fields)  # type: ignore[arg-type]
        except DomainError as exc:
            _abort(_render_error(exc))
        subjects = ", ".join(s.name for s in variants[0].subjects)
        console.print(
            f"Updated [bold]{variants[0].name}[/bold] across "
            f"[bold]{len(variants)}[/bold] level(s) — subjects: {subjects}."
        )


@packs_app.command("deactivate")
def packs_deactivate(pack_id: int = typer.Argument(...)) -> None:
    """Retire a pack: hidden when assigning, still shown on historical rows."""
    with _session() as session:
        try:
            pack = PackService(session).update(pack_id, is_active=False)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"Deactivated pack [bold]{pack.name} · {pack.level.value}[/bold].")


@packs_app.command("delete")
def packs_delete(
    pack_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Delete a pack nobody has ever been assigned to."""
    if not yes:
        typer.confirm(f"Delete pack {pack_id}?", abort=True)
    with _session() as session:
        try:
            PackService(session).delete(pack_id)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(f"Deleted pack [bold]{pack_id}[/bold].")


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
# debts
# --------------------------------------------------------------------------- #


@debts_app.command("list")
def debts_list() -> None:
    """Students who left owing money, largest debt first."""
    with _session() as session:
        service = DebtService(session)
        leavers = service.leavers_with_debt()
        table = Table(title="Left owing money")
        table.add_column("ID", justify="right")
        table.add_column("Name")
        table.add_column("Phone")
        table.add_column("Left on")
        table.add_column("Months", justify="right")
        table.add_column("Owed", justify="right")
        for status in leavers:
            table.add_row(
                str(status.student.id),
                status.student.full_name,
                status.student.phone or "—",
                status.left_on.isoformat() if status.left_on else "—",
                str(status.months_owed),
                f"{status.amount_owed}",
            )
        console.print(table)
        console.print(f"Total owed: [bold]{service.total_owed()}[/bold]")


@debts_app.command("write-off")
def debts_write_off(
    student_id: int = typer.Argument(...),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Forgive what a departed student owed. Recorded, and never counted as revenue."""
    with _session() as session:
        try:
            writeoff = DebtService(session).write_off(student_id, reason=reason)
        except DomainError as exc:
            _abort(_render_error(exc))
        console.print(
            f"Wrote off [bold]{writeoff.amount}[/bold] for student "
            f"[bold]{student_id}[/bold]: {writeoff.reason}"
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
        f"Seeded [bold]{summary.classes}[/bold] classes, "
        f"[bold]{summary.packs}[/bold] packs, "
        f"[bold]{summary.students}[/bold] students, "
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
