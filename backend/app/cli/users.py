"""`ardoise users`: the only way to create or recover an account.

There is no sign-up route (decision 0005). Because this talks to the database directly rather than
over HTTP, it keeps working when nobody can sign in: the break-glass tool when the last account
is lost or disabled.
"""

import typer
from rich.table import Table

from app.cli._common import abort, app, central_session, console, domain_errors
from app.core.db import central_url
from app.core.provisioning import migrate, provision_tenant
from app.services.auth_service import AuthService

users_app = typer.Typer(help="Accounts that can sign in to the app.", no_args_is_help=True)
app.add_typer(users_app, name="users")


@users_app.command("add")
def users_add(
    username: str = typer.Argument(..., help="Sign-in name; case-insensitive."),
    display_name: str = typer.Option(..., "--name", help='Shown in the app, e.g. "Aymen".'),
    password: str = typer.Option(
        ...,
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Prompted for (hidden) if omitted.",
    ),
) -> None:
    """Create an account that can sign in to the app, and its own private database."""
    # On a fresh host this runs before the app has ever started, so the accounts table may not
    # exist yet. Idempotent and quick on an existing database.
    migrate(central_url())

    with central_session() as session, domain_errors():
        user = AuthService(session).create_user(
            username=username, display_name=display_name, password=password
        )
        user_id, display, login = user.id, user.display_name, user.username

    # Their database is built after the account row commits, so the id is final. If this fails
    # the account exists without a database, which `ardoise db migrate` repairs; the other way
    # round, a database with no account, would be invisible.
    try:
        url = provision_tenant(user_id)
    except Exception as exc:  # noqa: BLE001 - the message matters more than the type here
        abort(
            f"Account '{display}' was created, but building its database failed ({exc}). "
            "Run `ardoise db migrate` to finish setting it up."
        )
    console.print(f"Created account [bold]{display}[/bold] ({login}).")
    console.print(f"Its data lives in [dim]{url}[/dim], separate from every other account.")


@users_app.command("list")
def users_list() -> None:
    """Every account, and whether it can sign in."""
    with central_session() as session:
        users = AuthService(session).list_users()
    if not users:
        console.print("[yellow]No accounts yet.[/yellow] Create one with: ardoise users add")
        return
    table = Table("ID", "Username", "Name", "Active", "Created")
    for user in users:
        table.add_row(
            str(user.id),
            user.username,
            user.display_name,
            "yes" if user.is_active else "no",
            user.created_at.date().isoformat(),
        )
    console.print(table)


@users_app.command("passwd")
def users_passwd(
    username: str = typer.Argument(...),
    password: str = typer.Option(
        ..., "--password", prompt=True, hide_input=True, confirmation_prompt=True
    ),
) -> None:
    """Set a new password. Signs the account out everywhere, which is the point if it leaked."""
    with central_session() as session, domain_errors():
        user = AuthService(session).set_password(username, password)
        console.print(
            f"Password updated for [bold]{user.username}[/bold]; all its sessions were revoked."
        )


@users_app.command("deactivate")
def users_deactivate(username: str = typer.Argument(...)) -> None:
    """Disable an account and sign it out at once. Reversible with `users activate`."""
    with central_session() as session, domain_errors():
        user = AuthService(session).set_active(username, False)
        console.print(f"Deactivated [bold]{user.username}[/bold] and revoked its sessions.")


@users_app.command("activate")
def users_activate(username: str = typer.Argument(...)) -> None:
    """Re-enable a disabled account. It will need to sign in again."""
    with central_session() as session, domain_errors():
        user = AuthService(session).set_active(username, True)
        console.print(f"Activated [bold]{user.username}[/bold].")
