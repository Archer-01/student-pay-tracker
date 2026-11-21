"""`ardoise db` and `ardoise openapi`: operations on the databases, and the API schema."""

import json
import os
from pathlib import Path

import typer
from alembic.config import Config

from alembic import command
from app.cli._common import abort, app, central_session, console
from app.core.backup import backup_database
from app.core.db import clear_engine_cache, tenant_url
from app.core.provisioning import migrate_all
from app.core.settings import settings
from app.services.auth_service import AuthService

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

db_app = typer.Typer(help="Migrations, backups, and a dev-only reset.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("migrate")
def db_migrate() -> None:
    """Bring the central database and every teacher's up to date.

    The app does this on every start; this is for repairing an account whose database failed to
    build, or applying a migration without a restart.
    """
    with central_session() as session:
        user_ids = [user.id for user in AuthService(session).list_users()]
    failed = migrate_all(user_ids)
    console.print(f"Migrated the central database and {len(user_ids) - len(failed)} teacher(s).")
    if failed:
        abort(f"Failed for user id(s): {', '.join(str(i) for i in failed)}; see the log.")


@db_app.command("backup")
def db_backup(
    to: Path = typer.Option(Path("backups"), "--to", help="Destination directory."),
) -> None:
    """Back up every database, the accounts and each teacher's, safe while the app runs.

    Backing up only the central file would save who can sign in and none of the students.
    Keep the copies off the host: the volume is the only other copy (decision 0004).
    """
    sources = [settings.database_url]
    with central_session() as session:
        sources += [tenant_url(user.id) for user in AuthService(session).list_users()]

    written = []
    for source in sources:
        try:
            written.append(backup_database(source, to))
        except ValueError as exc:
            # A teacher whose database was never built is no reason to fail the whole backup.
            console.print(f"[yellow]Skipped[/yellow] {source}: {exc}")
    if not written:
        abort("Nothing was backed up.")
    console.print(f"Backed up [bold]{len(written)}[/bold] database(s) to [bold]{to}[/bold].")


@db_app.command("reset")
def db_reset(
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Drop and recreate the central (accounts) database. Dev only: needs ALLOW_DB_RESET=1."""
    if os.environ.get("ALLOW_DB_RESET") != "1":
        abort("Refusing to reset: set ALLOW_DB_RESET=1 to allow this (dev only).")
    if not yes:
        typer.confirm("This will DROP and recreate every table. Continue?", abort=True)
    clear_engine_cache()
    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    console.print(f"Database reset to a clean migrated state ({settings.database_url}).")
    console.print(
        "[yellow]Note:[/yellow] only the central account database. A teacher's data lives in "
        "its own file; delete that file to reset it."
    )


@app.command("openapi")
def openapi_dump() -> None:
    """Print the API schema as JSON (what `npm run gen:api` reads).

    No server and no session needed: /openapi.json is gated like every other route. Printed with
    `typer.echo`, not Rich, so the output is plain JSON for a pipe.
    """
    from app.main import app as fastapi_app

    typer.echo(json.dumps(fastapi_app.openapi(), indent=2))
