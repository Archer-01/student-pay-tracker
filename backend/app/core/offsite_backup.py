"""The nightly off-site copy (decision 0012).

Every database (the accounts and each teacher's) is copied safely while the app runs, packed in
one archive, encrypted to the developer's public key with `age`, and posted to a small Apps Script
in the developer's Google account, which files it in Drive (`backend/ops/backup-drop.gs`). The
server only ever holds the public key: nobody who gets the files, or the Drive, can read them.
Decrypting needs the private key, kept by the developer (`ardoise backup restore`, or the `age`
tool itself). Setup and restore steps: `docs/backups.md`.

The volume can only be mounted by this service, so the app does this itself, on a schedule
(:func:`backup_loop`), rather than a separate job.
"""

import asyncio
import base64
import io
import json
import logging
import sqlite3
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
import pyrage
from pyrage import x25519
from sqlalchemy.engine import make_url

from app.core.backup import backup_database

MOROCCO = ZoneInfo("Africa/Casablanca")
# The developer is alerted by this going stale, not by a single missed night.
STALE_AFTER = timedelta(hours=48)
# A restart more than this long after the last copy makes one at once, not at the next 3 a.m.
CATCH_UP_AFTER = timedelta(hours=24)

log = logging.getLogger("app.backup")

BackupHealth = Literal["ok", "partial", "stale", "off"]


class BackupError(Exception):
    """The copy, the encryption or the upload failed; the message says which."""


@dataclass(frozen=True)
class BackupConfig:
    url: str  # the Apps Script web app's address
    secret: str  # what the script checks before saving anything
    public_key: str  # an age recipient, "age1…"
    hour: int = 3  # Morocco time


@dataclass
class BackupStatus:
    last_success: str | None = None  # ISO timestamps, UTC
    last_attempt: str | None = None
    last_error: str | None = None
    last_name: str | None = None
    # Databases the last good copy had to leave out (absent or unreadable): it is "partial".
    skipped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Archive:
    data: bytes  # the .tar.gz, not yet encrypted
    included: list[str]  # file names, as in the archive
    skipped: list[str]


@dataclass(frozen=True)
class BackupResult:
    name: str
    included: list[str]
    skipped: list[str]


def status_path(central_database_url: str) -> Path | None:
    """`backup-status.json` beside the central database, or None for an in-memory one."""
    url = make_url(central_database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).parent / "backup-status.json"


def read_status(path: Path | None) -> BackupStatus:
    if path is None or not path.exists():
        return BackupStatus()
    try:
        return BackupStatus(**json.loads(path.read_text()))
    except (ValueError, TypeError):
        log.warning("unreadable backup status at %s; starting afresh", path)
        return BackupStatus()


def write_status(path: Path | None, status: BackupStatus) -> None:
    if path is not None:
        path.write_text(json.dumps(asdict(status), indent=2))


def health(status: BackupStatus, *, configured: bool, now: datetime) -> BackupHealth:
    """ "off" when not set up, "stale" when there's been no good copy for two days, "partial"
    when the last copy had to leave a database out."""
    if not configured:
        return "off"
    if status.last_success is None:
        return "stale"
    if now - datetime.fromisoformat(status.last_success) >= STALE_AFTER:
        return "stale"
    return "partial" if status.skipped else "ok"


def next_run(now: datetime, hour: int = 3) -> datetime:
    """The next `hour`:00 in Morocco after `now` (both timezone-aware)."""
    local = now.astimezone(MOROCCO)
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def due_now(status: BackupStatus, now: datetime) -> bool:
    """At startup: copy at once if the last good copy is over a day old (or there is none)."""
    if status.last_success is None:
        return True
    return now - datetime.fromisoformat(status.last_success) >= CATCH_UP_AFTER


def build_archive(database_urls: Sequence[str]) -> Archive:
    """A .tar.gz of a consistent copy of each database. One that can't be copied (absent,
    damaged) is skipped and named, so one teacher's bad file never costs the others their copy."""
    with tempfile.TemporaryDirectory() as workdir:
        copies, skipped = [], []
        for url in database_urls:
            try:
                copies.append(backup_database(url, Path(workdir)))
            except Exception as exc:  # noqa: BLE001 - whatever it is, the others still go
                log.warning("backup skipped %s: %s", url, exc)
                skipped.append(Path(make_url(url).database or url).name)
        if not copies:
            raise BackupError("no database to back up")
        buffer = io.BytesIO()
        # The copy's name without its timestamp: "central.db", "tenant-1.db".
        names = [copy.name.split("-", 3)[-1] for copy in copies]
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for copy, name in zip(copies, names, strict=True):
                archive.add(copy, arcname=name)
        return Archive(buffer.getvalue(), names, skipped)


def encrypt(data: bytes, public_key: str) -> bytes:
    try:
        return bytes(pyrage.encrypt(data, [x25519.Recipient.from_str(public_key.strip())]))
    except Exception as exc:  # noqa: BLE001 - pyrage raises its own types; the message is enough
        raise BackupError(f"encryption failed: {exc}") from exc


def decrypt(data: bytes, private_key: str) -> bytes:
    return bytes(pyrage.decrypt(data, [x25519.Identity.from_str(private_key.strip())]))


def generate_keys() -> tuple[str, str]:
    """(public key for the server, private key for the developer's password manager)."""
    identity = x25519.Identity.generate()
    return str(identity.to_public()), str(identity)


def upload(name: str, payload: bytes, config: BackupConfig, client: httpx.Client) -> None:
    """Post the encrypted archive to the Apps Script, which answers {"ok": true} once saved.
    Apps Script answers a POST with a redirect to its result, hence follow_redirects."""
    body = {"secret": config.secret, "name": name, "data": base64.b64encode(payload).decode()}
    try:
        response = client.post(config.url, json=body, follow_redirects=True, timeout=60)
        answer = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BackupError(f"upload failed: {exc}") from exc
    if not isinstance(answer, dict):
        raise BackupError(f"upload refused: unexpected answer ({response.status_code})")
    if not answer.get("ok"):
        raise BackupError(f"upload refused: {answer.get('error', response.status_code)}")


def run_backup(
    database_urls: Sequence[str],
    config: BackupConfig,
    status_file: Path | None,
    *,
    now: datetime,
    client: httpx.Client | None = None,
) -> BackupResult:
    """Copy, encrypt and upload once; record the outcome either way, whatever went wrong (any
    failure comes out as a BackupError)."""
    status = read_status(status_file)
    status.last_attempt = now.isoformat()
    name = f"ardoise-{now:%Y%m%d-%H%M%S}.tar.gz.age"
    try:
        archive = build_archive(database_urls)
        payload = encrypt(archive.data, config.public_key)
        if client is not None:  # the caller's, and the caller closes it
            upload(name, payload, config, client)
        else:
            with httpx.Client() as http:
                upload(name, payload, config, http)
    except Exception as exc:  # noqa: BLE001 - recorded either way, so /health can tell
        status.last_error = str(exc) if isinstance(exc, BackupError) else f"backup crashed: {exc}"
        write_status(status_file, status)
        log.error("backup failed: %s", status.last_error)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(status.last_error) from exc
    status.last_success, status.last_error, status.last_name = now.isoformat(), None, name
    status.skipped = archive.skipped
    write_status(status_file, status)
    log.info("backup %s uploaded (%d bytes)", name, len(payload))
    if archive.skipped:
        log.error("backup %s left out %s", name, ", ".join(archive.skipped))
    return BackupResult(name, archive.included, archive.skipped)


def restore(archive: bytes, private_key: str, destination: Path) -> list[Path]:
    """Decrypt an archive and unpack its databases into `destination`, each one checked.

    Never touches the live databases: putting a restored file in place is a deliberate,
    documented step (docs/backups.md). So a folder already holding databases is refused: pointed
    at the live data folder by mistake, this would overwrite it with an old copy.
    """
    if destination.is_dir() and any(destination.glob("*.db")):
        raise BackupError(f"{destination} already holds databases: restore into an empty folder")
    try:
        plain = decrypt(archive, private_key)
    except Exception as exc:  # noqa: BLE001 - a wrong key and a damaged file both land here
        raise BackupError(f"could not decrypt the backup: {exc}") from exc
    destination.mkdir(parents=True, exist_ok=True)
    restored = []
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
        for member in tar.getmembers():
            # Plain files only, by their bare name: an archive can't write outside `destination`.
            if not member.isfile() or not member.name.endswith(".db"):
                continue
            source = tar.extractfile(member)
            assert source is not None
            target = destination / Path(member.name).name
            target.write_bytes(source.read())
            try:
                with sqlite3.connect(target) as conn:
                    check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.DatabaseError as exc:  # not even readable as a database
                check = str(exc)
            if check != "ok":
                raise BackupError(f"{target.name} failed its integrity check: {check}")
            restored.append(target)
    if not restored:
        raise BackupError("the archive holds no database")
    return restored


async def backup_loop(
    database_urls: Callable[[], Sequence[str]],
    config: BackupConfig,
    status_file: Path | None,
) -> None:
    """Run for the life of the app: once at startup if overdue, then every night at `hour`.
    A failure is logged and recorded, and the loop carries on to the next night."""

    async def once() -> None:
        try:
            await asyncio.to_thread(
                run_backup, database_urls(), config, status_file, now=datetime.now(UTC)
            )
        except BackupError:
            pass  # recorded in the status file and the log by run_backup
        except Exception:  # noqa: BLE001 - never let the loop die
            log.exception("backup crashed")

    if due_now(read_status(status_file), datetime.now(UTC)):
        await once()
    while True:
        wait = next_run(datetime.now(UTC), config.hour) - datetime.now(UTC)
        await asyncio.sleep(wait.total_seconds())
        await once()
