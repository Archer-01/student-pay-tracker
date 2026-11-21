"""`ardoise students`: look a student up, or delete one for good.

Enrolling, editing, payments and leaving are done in the app (decision 0010). What stays here is
what support from a terminal needs, plus the hard delete the app deliberately doesn't offer.
"""

import typer

from app.cli._common import (
    app,
    class_label,
    console,
    domain_errors,
    find_student,
    money,
    parse_date,
    table,
    teacher_session,
)
from app.models import StudentStatus
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PricingService
from app.services.student_service import StudentService

students_app = typer.Typer(help="Look up students, or delete one.", no_args_is_help=True)
app.add_typer(students_app, name="students")

_AS_OF_HELP = "Figures as of this day, YYYY-MM-DD (default: today)."


def _months(count: int) -> str:
    return f"{count} month" if count == 1 else f"{count} months"


@students_app.command("list")
def students_list(
    status: StudentStatus | None = typer.Option(None, "--status", help="active or inactive."),
    search: str | None = typer.Option(None, "--search", help="A piece of the name."),
    owing: bool = typer.Option(False, "--owing", help="Only students who owe something."),
    as_of: str | None = typer.Option(None, "--as-of", help=_AS_OF_HELP),
) -> None:
    """Students with their class, price and what they owe; most owed first."""
    day = parse_date(as_of)
    with teacher_session() as session:
        ledger, pricing = LedgerService(session), PricingService(session)
        rows = [
            (student, ledger.student_summary(student.id, day))
            for student in StudentService(session).list(status=status, query=search)
        ]
        if owing:
            rows = [(s, summary) for s, summary in rows if summary.amount_owed > 0]
        rows.sort(key=lambda row: (-row[1].amount_owed, row[0].full_name.casefold()))

        view = table(
            f"Students, as of {day}", ">ID", "Name", "Class", ">Price", ">Owed", ">Days late"
        )
        for student, summary in rows:
            owed = (
                f"{money(summary.amount_owed)} ({summary.months_overdue} mo)"
                if summary.amount_owed > 0
                else "—"
            )
            view.add_row(
                str(student.id),
                student.full_name if student.status is StudentStatus.ACTIVE
                else f"{student.full_name} (left)",
                class_label(student.school_class),
                money(pricing.price_of(student)),
                owed,
                str(summary.cumulative_drift),
            )  # fmt: skip
        console.print(view)


@students_app.command("show")
def students_show(
    student: str = typer.Argument(..., help="Id, or a piece of the name."),
    as_of: str | None = typer.Option(None, "--as-of", help=_AS_OF_HELP),
) -> None:
    """One student: the facts the app shows, then every month due and how it was paid."""
    day = parse_date(as_of)
    with teacher_session() as session:
        found = find_student(session, student)
        with domain_errors():
            summary = LedgerService(session).student_summary(found.id, day)
            entries = LedgerService(session).get_ledger(found.id, day)
        price = PricingService(session).price_of(found)

        console.print(f"[bold]{found.full_name}[/bold] (id {found.id}), as of {day}")
        facts = [
            ("Status", "left" if found.status is StudentStatus.INACTIVE else "attending"),
            ("Class", class_label(found.school_class)),
            ("Pack", found.pack.name if found.pack else "—"),
            ("Price", money(price) + (f"  ({found.price_note})" if found.price_note else "")),
            ("Phone", found.phone or "—"),
            ("Joined", found.join_date.isoformat()),
            ("Owed", f"{money(summary.amount_owed)} ({_months(summary.months_overdue)})"),
            ("Next due", summary.next_expected_date.isoformat()),
            ("Paid so far", f"{money(summary.total_paid)} in {summary.payments_count} payments"),
            ("Days late", f"{summary.cumulative_drift} in total, "
             + ("no payment due yet" if summary.average_days_late is None
                else f"{summary.average_days_late} on average lately")),
            ("Note", found.note or "—"),
        ]  # fmt: skip
        for label, value in facts:
            console.print(f"  [dim]{label:<12}[/dim]{value}")

        view = table("Months", "Month", "Due", "Paid", ">Days late", ">Amount", "")
        for entry in entries:
            if entry.paid_date is not None:
                state = "late" if (entry.days_late or 0) > 0 else "paid"
            else:
                state = "away" if entry.suspended else "unpaid"
            view.add_row(
                entry.expected_due_date.strftime("%Y-%m"),
                entry.expected_due_date.isoformat(),
                entry.paid_date.isoformat() if entry.paid_date else "—",
                str(entry.days_late) if entry.days_late is not None else "—",
                money(entry.amount),
                state,
            )
        console.print(view)


@students_app.command("delete")
def students_delete(
    student: str = typer.Argument(..., help="Id, or a piece of the name."),
) -> None:
    """Delete a student and everything recorded for them, for good.

    The app never does this: a student who leaves is marked as left and keeps their history.
    This is for a record that should never have existed (a duplicate, a test). It asks you to type
    the student's full name.
    """
    with teacher_session() as session:
        found = find_student(session, student)
        console.print(
            f"This deletes [bold]{found.full_name}[/bold] (id {found.id}) with all their "
            "payments, absences and overrides. It cannot be undone."
        )
        typed = typer.prompt("Type their full name to confirm")
        if typed.strip().casefold() != found.full_name.casefold():
            console.print("Names don't match; nothing was deleted.")
            raise typer.Exit(code=1)
        with domain_errors():
            StudentService(session).delete(found.id)
        console.print(f"Deleted [bold]{found.full_name}[/bold].")
