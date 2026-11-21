"""`ardoise debts` and `ardoise share`: who left owing, and the school's share, read only."""

import typer

from app.cli._common import app, console, money, parse_date, table, teacher_session
from app.core.settings import settings
from app.services.debt_service import DebtService
from app.services.school_share_handover_service import SchoolShareHandoverService

debts_app = typer.Typer(help="Students who left owing money.", no_args_is_help=True)
share_app = typer.Typer(help="The school's share of each month.", no_args_is_help=True)
app.add_typer(debts_app, name="debts")
app.add_typer(share_app, name="share")


@debts_app.command("list")
def debts_list() -> None:
    """Students who left owing money, largest debt first."""
    with teacher_session() as session:
        service = DebtService(session)
        view = table("Left owing money", ">ID", "Name", "Phone", "Left on", ">Months", ">Owed")
        for status in service.leavers_with_debt():
            view.add_row(
                str(status.student.id),
                status.student.full_name,
                status.student.phone or "—",
                status.left_on.isoformat() if status.left_on else "—",
                str(status.months_owed),
                money(status.amount_owed),
            )
        console.print(view)
        console.print(f"Total owed: [bold]{money(service.total_owed())}[/bold]")


@share_app.command("list")
def share_list(
    as_of: str | None = typer.Option(None, "--as-of", help="YYYY-MM-DD (default: today)."),
) -> None:
    """Each month's share for the school, and whether it was handed over; newest first."""
    percent = settings.school_share_percent
    with teacher_session() as session:
        months = SchoolShareHandoverService(session).months(parse_date(as_of), percent)
    if not months:
        console.print("No share to show (no payments yet, or the share is 0 %).")
        return
    view = table(
        f"School's share ({percent} % of what came in)",
        "Month",
        ">Came in",
        ">Share",
        "Status",
        "Handed on",
        ">To hand over",
    )
    for month in months:
        view.add_row(
            f"{month.year}-{month.month:02d}",
            money(month.collected),
            money(month.due),
            month.status,
            month.handed_on.isoformat() if month.handed_on else "—",
            money(month.remaining) if month.remaining > 0 else "—",
        )
    console.print(view)
