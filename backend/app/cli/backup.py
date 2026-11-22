"""`ardoise backup`: the nightly off-site copy (decision 0012, docs/backups.md).

`keygen` once, on your own machine; `run` from the server to check the setup end to end;
`restore` on your machine, to read a copy back. (`ardoise db backup` is the local, unencrypted
copy into a folder on the same disk.)
"""

from datetime import UTC, datetime
from pathlib import Path

import typer

from app.cli._common import abort, app, central_session, console
from app.core.db import central_url, tenant_url
from app.core.offsite_backup import (
    BackupError,
    generate_keys,
    read_status,
    restore,
    run_backup,
    status_path,
)
from app.core.settings import settings
from app.services.auth_service import AuthService

backup_app = typer.Typer(help="The nightly encrypted copy to Google Drive.", no_args_is_help=True)
app.add_typer(backup_app, name="backup")


@backup_app.command("keygen")
def backup_keygen() -> None:
    """Make the key pair. The public key goes to the server (BACKUP_PUBLIC_KEY); the private
    key goes in your password manager, and nowhere near the server."""
    public, private = generate_keys()
    console.print(f"Public key, for BACKUP_PUBLIC_KEY on the server:\n  [bold]{public}[/bold]\n")
    console.print(
        "Private key, for your password manager (and one more safe copy). Without it no backup\n"
        f"can ever be read, by anyone:\n  [bold]{private}[/bold]"
    )


@backup_app.command("run")
def backup_run() -> None:
    """Make an off-site copy now, as the nightly one would, and say how it went."""
    config = settings.backup_config()
    if config is None:
        abort("Not set up: BACKUP_URL, BACKUP_SECRET and BACKUP_PUBLIC_KEY are all needed.")
    with central_session() as session:
        urls = [central_url(), *(tenant_url(u.id) for u in AuthService(session).list_users())]
    try:
        result = run_backup(urls, config, status_path(central_url()), now=datetime.now(UTC))
    except BackupError as exc:
        abort(str(exc))
    console.print(f"Uploaded [bold]{result.name}[/bold] ({len(result.included)} database(s)).")
    if result.skipped:
        console.print(f"[red]Left out (absent or unreadable):[/red] {', '.join(result.skipped)}")


@backup_app.command("status")
def backup_status() -> None:
    """When the last off-site copy was made, and the last error if the latest attempt failed."""
    status = read_status(status_path(central_url()))
    console.print(f"Configured:   {'yes' if settings.backup_config() else 'no'}")
    console.print(f"Last success: {status.last_success or 'never'}  {status.last_name or ''}")
    console.print(f"Last attempt: {status.last_attempt or 'never'}")
    if status.skipped:
        console.print(f"[red]Left out:[/red]     {', '.join(status.skipped)}")
    if status.last_error:
        console.print(f"[red]Last error:[/red]   {status.last_error}")


@backup_app.command("restore")
def backup_restore(
    archive: Path = typer.Argument(..., exists=True, dir_okay=False, help="A .tar.gz.age file."),
    key_file: Path = typer.Option(
        ..., "--key-file", exists=True, dir_okay=False, help="A file holding the private key."
    ),
    to: Path = typer.Option(Path("restored"), "--to", help="Where to put the databases."),
) -> None:
    """Decrypt a copy and unpack its databases into a folder, each one checked.

    Never touches the live databases; putting them in place is a separate step
    (docs/backups.md).
    """
    try:
        restored = restore(archive.read_bytes(), key_file.read_text(), to)
    except BackupError as exc:
        abort(str(exc))
    for path in restored:
        console.print(f"Restored and checked [bold]{path}[/bold]")
