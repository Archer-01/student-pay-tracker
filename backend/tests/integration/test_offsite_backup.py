"""The nightly off-site copy (decision 0012): archive, encryption, upload, status, schedule and
restore. Uploads go to a fake Apps Script (httpx.MockTransport); nothing leaves the machine."""

import asyncio
import base64
import io
import json
import sqlite3
import tarfile
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from app.cli import app as cli
from app.core import offsite_backup as ob
from app.core.settings import settings

NOW = datetime(2026, 11, 22, 2, 0, tzinfo=UTC)
_RealClient = httpx.Client
PUBLIC, PRIVATE = ob.generate_keys()


def _database(path: Path, rows: int = 3) -> str:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE student (id INTEGER PRIMARY KEY, name TEXT)")
        conn.executemany("INSERT INTO student (name) VALUES (?)", [(f"s{i}",) for i in range(rows)])
    return f"sqlite:///{path}"


@pytest.fixture
def databases(tmp_path: Path) -> list[str]:
    data = tmp_path / "data"
    data.mkdir()
    return [_database(data / "central.db", 1), _database(data / "tenant-1.db", 3)]


def _config(**over: object) -> ob.BackupConfig:
    values: dict[str, object] = {
        "url": "https://script.test/exec",
        "secret": "s3cret",
        "public_key": PUBLIC,
    } | over
    return ob.BackupConfig(**values)  # type: ignore[arg-type]


class FakeScript:
    """Answers like the Apps Script: a redirect to its result, then {"ok": true}."""

    def __init__(self, answer: dict[str, object] | None = None) -> None:
        self.answer = answer or {"ok": True}
        self.received: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.received.append(json.loads(request.content))
            return httpx.Response(302, headers={"location": "https://script.test/result"})
        return httpx.Response(200, json=self.answer)

    def client(self) -> httpx.Client:
        # The real class, saved below: some tests replace httpx.Client itself.
        return _RealClient(transport=httpx.MockTransport(self))


def _members(encrypted: bytes) -> dict[str, bytes]:
    plain = ob.decrypt(encrypted, PRIVATE)
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers()}  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# A copy
# --------------------------------------------------------------------------- #


def test_a_backup_is_every_database_encrypted_and_posted(
    databases: list[str], tmp_path: Path
) -> None:
    script, status_file = FakeScript(), tmp_path / "status.json"
    result = ob.run_backup(databases, _config(), status_file, now=NOW, client=script.client())
    name = result.name

    assert name == "ardoise-20261122-020000.tar.gz.age"
    assert (result.included, result.skipped) == (["central.db", "tenant-1.db"], [])
    sent = script.received[0]
    assert sent["secret"] == "s3cret" and sent["name"] == name
    archive = base64.b64decode(sent["data"])
    assert not archive.startswith(b"\x1f\x8b")  # not a readable gzip: encrypted first
    assert set(_members(archive)) == {"central.db", "tenant-1.db"}

    status = ob.read_status(status_file)
    assert status.last_success == NOW.isoformat() and status.last_error is None


@pytest.mark.parametrize("missing", [None, b"x" * 4096], ids=["absent", "damaged"])
def test_a_database_that_cant_be_copied_is_skipped_and_the_copy_is_partial(
    databases: list[str], tmp_path: Path, missing: bytes | None
) -> None:
    # One teacher's damaged file must not cost every other teacher their copy, nor pass unseen.
    bad = tmp_path / "data" / "tenant-9.db"
    if missing is not None:
        bad.write_bytes(missing)
    script, status_file = FakeScript(), tmp_path / "status.json"
    urls = [*databases, f"sqlite:///{bad}"]
    result = ob.run_backup(urls, _config(), status_file, now=NOW, client=script.client())
    assert set(_members(base64.b64decode(script.received[0]["data"]))) == {
        "central.db",
        "tenant-1.db",
    }
    assert result.skipped == ["tenant-9.db"]
    status = ob.read_status(status_file)
    assert status.last_success == NOW.isoformat() and status.skipped == ["tenant-9.db"]
    assert ob.health(status, configured=True, now=NOW) == "partial"


def test_nothing_to_back_up_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ob.BackupError, match="no database"):
        ob.build_archive([f"sqlite:///{tmp_path / 'missing.db'}"])


@pytest.mark.parametrize("answer", [[1, 2], "ok", 42])
def test_an_odd_answer_from_the_script_is_a_recorded_failure(
    databases: list[str], tmp_path: Path, answer: object
) -> None:
    def script(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer)

    status_file = tmp_path / "status.json"
    with (
        _RealClient(transport=httpx.MockTransport(script)) as client,
        pytest.raises(ob.BackupError, match="upload refused"),
    ):
        ob.run_backup(databases, _config(), status_file, now=NOW, client=client)
    assert ob.read_status(status_file).last_error is not None


def test_any_failure_is_recorded_as_a_backup_error(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(data: bytes, key: str) -> bytes:
        raise RuntimeError("disk full")

    monkeypatch.setattr(ob, "encrypt", boom)
    status_file = tmp_path / "status.json"
    with pytest.raises(ob.BackupError, match="disk full"):
        ob.run_backup(databases, _config(), status_file, now=NOW, client=FakeScript().client())
    assert "disk full" in (ob.read_status(status_file).last_error or "")


def test_a_refused_upload_is_recorded_and_raised(databases: list[str], tmp_path: Path) -> None:
    status_file = tmp_path / "status.json"
    ob.write_status(status_file, ob.BackupStatus(last_success="2026-11-21T02:00:00+00:00"))
    script = FakeScript({"ok": False, "error": "forbidden"})
    with pytest.raises(ob.BackupError, match="forbidden"):
        ob.run_backup(databases, _config(), status_file, now=NOW, client=script.client())
    status = ob.read_status(status_file)
    assert status.last_error == "upload refused: forbidden"
    assert status.last_success == "2026-11-21T02:00:00+00:00"  # the last good one stays
    assert status.last_attempt == NOW.isoformat()


def test_an_unreachable_script_is_a_backup_error(databases: list[str]) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(down)) as client,
        pytest.raises(ob.BackupError, match="upload failed"),
    ):
        ob.run_backup(databases, _config(), None, now=NOW, client=client)


def test_a_bad_public_key_is_a_backup_error(databases: list[str]) -> None:
    with pytest.raises(ob.BackupError, match="encryption failed"):
        ob.run_backup(databases, _config(public_key="age1nope"), None, now=NOW)


# --------------------------------------------------------------------------- #
# Reading a copy back
# --------------------------------------------------------------------------- #


def test_restore_gives_back_checked_databases(databases: list[str], tmp_path: Path) -> None:
    archive = ob.encrypt(ob.build_archive(databases).data, PUBLIC)
    restored = ob.restore(archive, PRIVATE, tmp_path / "restored")
    assert sorted(p.name for p in restored) == ["central.db", "tenant-1.db"]
    with sqlite3.connect(tmp_path / "restored" / "tenant-1.db") as conn:
        assert conn.execute("SELECT count(*) FROM student").fetchone()[0] == 3


def test_restore_refuses_a_folder_that_already_holds_databases(
    databases: list[str], tmp_path: Path
) -> None:
    # `--to` pointed at the live data folder would overwrite it with an old copy.
    archive = ob.encrypt(ob.build_archive(databases).data, PUBLIC)
    target = tmp_path / "data"  # where `databases` live
    before = (target / "tenant-1.db").read_bytes()
    with pytest.raises(ob.BackupError, match="already holds"):
        ob.restore(archive, PRIVATE, target)
    assert (target / "tenant-1.db").read_bytes() == before


def test_restore_refuses_the_wrong_key(databases: list[str], tmp_path: Path) -> None:
    archive = ob.encrypt(ob.build_archive(databases).data, PUBLIC)
    _, someone_else = ob.generate_keys()
    with pytest.raises(ob.BackupError, match="could not decrypt"):
        ob.restore(archive, someone_else, tmp_path / "restored")


def _archive_of(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return ob.encrypt(buffer.getvalue(), PUBLIC)


def test_restore_never_writes_outside_its_folder(databases: list[str], tmp_path: Path) -> None:
    good = Path(databases[1].removeprefix("sqlite:///")).read_bytes()
    archive = _archive_of({"../../evil.db": good, "notes.txt": b"x"})
    restored = ob.restore(archive, PRIVATE, tmp_path / "restored")
    assert restored == [tmp_path / "restored" / "evil.db"]
    assert not (tmp_path / "evil.db").exists()


def test_restore_refuses_a_damaged_database_or_an_empty_archive(tmp_path: Path) -> None:
    with pytest.raises(ob.BackupError, match="failed its integrity check"):
        ob.restore(_archive_of({"central.db": b"x" * 4096}), PRIVATE, tmp_path / "a")
    with pytest.raises(ob.BackupError, match="no database"):
        ob.restore(_archive_of({"notes.txt": b"x"}), PRIVATE, tmp_path / "b")


# --------------------------------------------------------------------------- #
# Status, schedule, health
# --------------------------------------------------------------------------- #


def test_status_lives_beside_the_central_database() -> None:
    assert ob.status_path("sqlite:////data/central.db") == Path("/data/backup-status.json")
    assert ob.status_path("sqlite://") is None
    assert ob.read_status(None) == ob.BackupStatus()
    ob.write_status(None, ob.BackupStatus())  # no file to write: a no-op


def test_an_unreadable_status_file_starts_afresh(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text("{not json")
    assert ob.read_status(tmp_path / "status.json") == ob.BackupStatus()


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Morocco's offset comes from the timezone database, never hard-coded.
        (datetime(2026, 11, 22, 1, 0, tzinfo=UTC), datetime(2026, 11, 22, 3, 0, tzinfo=UTC)),
        (datetime(2026, 11, 22, 3, 0, tzinfo=UTC), datetime(2026, 11, 23, 3, 0, tzinfo=UTC)),
        (datetime(2026, 7, 1, 1, 0, tzinfo=UTC), datetime(2026, 7, 1, 2, 0, tzinfo=UTC)),
    ],
)
def test_the_next_run_is_3_am_in_morocco(now: datetime, expected: datetime) -> None:
    assert ob.next_run(now, 3) == expected


def test_a_restart_catches_up_only_after_a_day() -> None:
    assert ob.due_now(ob.BackupStatus(), NOW)
    recent = ob.BackupStatus(last_success=(NOW - timedelta(hours=5)).isoformat())
    old = ob.BackupStatus(last_success=(NOW - timedelta(hours=30)).isoformat())
    assert not ob.due_now(recent, NOW)
    assert ob.due_now(old, NOW)


def test_health_is_off_ok_or_stale() -> None:
    fresh = ob.BackupStatus(last_success=(NOW - timedelta(hours=20)).isoformat())
    stale = ob.BackupStatus(last_success=(NOW - timedelta(hours=49)).isoformat())
    assert ob.health(fresh, configured=False, now=NOW) == "off"
    assert ob.health(fresh, configured=True, now=NOW) == "ok"
    assert ob.health(stale, configured=True, now=NOW) == "stale"
    assert ob.health(ob.BackupStatus(), configured=True, now=NOW) == "stale"
    partial = ob.BackupStatus(last_success=fresh.last_success, skipped=["tenant-2.db"])
    assert ob.health(partial, configured=True, now=NOW) == "partial"
    stale_partial = ob.BackupStatus(last_success=stale.last_success, skipped=["tenant-2.db"])
    assert ob.health(stale_partial, configured=True, now=NOW) == "stale"


def test_settings_need_all_three_values(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings.backup_config() is None
    monkeypatch.setattr(settings, "backup_url", "https://script.test/exec")
    monkeypatch.setattr(settings, "backup_secret", "s3cret")
    assert settings.backup_config() is None
    monkeypatch.setattr(settings, "backup_public_key", PUBLIC)
    config = settings.backup_config()
    assert config is not None and config.hour == 3


async def test_health_reports_the_backup_without_failing(
    anonymous_client: httpx.AsyncClient,
) -> None:
    body = (await anonymous_client.get("/health")).json()
    assert body == {"status": "ok", "database": "ok", "backup": "off"}


async def test_the_loop_backs_up_when_overdue_then_waits_for_3_am(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = FakeScript()
    monkeypatch.setattr(ob.httpx, "Client", lambda: script.client())
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(ob.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await ob.backup_loop(lambda: databases, _config(), tmp_path / "status.json")
    assert len(script.received) == 1  # overdue at startup: one copy at once
    assert 0 < slept[0] <= 24 * 3600  # then until the next 3 a.m.


async def test_the_loop_waits_when_the_last_copy_is_recent(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_file = tmp_path / "status.json"
    ob.write_status(status_file, ob.BackupStatus(last_success=datetime.now(UTC).isoformat()))
    script = FakeScript()
    monkeypatch.setattr(ob.httpx, "Client", lambda: script.client())

    async def sleep(seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(ob.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await ob.backup_loop(lambda: databases, _config(), status_file)
    assert script.received == []  # nothing at startup: the next copy is at 3 a.m.


async def test_the_loop_survives_a_failed_night(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ob.httpx, "Client", lambda: FakeScript({"ok": False}).client())
    calls = 0

    async def sleep(seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(ob.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await ob.backup_loop(lambda: databases, _config(), tmp_path / "status.json")
    assert ob.read_status(tmp_path / "status.json").last_error is not None


async def test_the_loop_survives_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> list[str]:
        raise RuntimeError("database gone")

    async def sleep(seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(ob.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await ob.backup_loop(boom, _config(), tmp_path / "status.json")


async def test_the_app_starts_the_loop_only_when_set_up(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    assert main._start_backups() is None
    monkeypatch.setattr(settings, "backup_url", "https://script.test/exec")
    monkeypatch.setattr(settings, "backup_secret", "s3cret")
    monkeypatch.setattr(settings, "backup_public_key", PUBLIC)
    seen: list[list[str]] = []

    async def loop(urls, config, status_file) -> None:  # type: ignore[no-untyped-def]
        seen.append(list(urls()))

    def accounts():  # type: ignore[no-untyped-def]
        yield SimpleNamespace(scalars=lambda query: [1, 2], close=lambda: None)

    monkeypatch.setattr(settings, "database_url", "sqlite:////data/central.db")
    monkeypatch.setattr("app.core.db.get_auth_db", accounts)
    monkeypatch.setattr("app.core.offsite_backup.backup_loop", loop)
    task = main._start_backups()
    assert task is not None
    await task
    assert seen == [
        ["sqlite:////data/central.db", "sqlite:////data/tenant-1.db", "sqlite:////data/tenant-2.db"]
    ]


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #

runner = CliRunner()


def test_cli_keygen_prints_a_working_pair() -> None:
    out = runner.invoke(cli, ["backup", "keygen"]).output
    public = next(w for w in out.split() if w.startswith("age1"))
    private = next(w for w in out.split() if w.startswith("AGE-SECRET-KEY-"))
    assert ob.decrypt(ob.encrypt(b"x", public), private) == b"x"


def test_cli_run_needs_the_settings() -> None:
    result = runner.invoke(cli, ["backup", "run"])
    assert result.exit_code == 1
    assert "BACKUP_URL" in result.output


def test_cli_run_status_and_restore(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", databases[0])
    monkeypatch.setattr(settings, "backup_url", "https://script.test/exec")
    monkeypatch.setattr(settings, "backup_secret", "s3cret")
    monkeypatch.setattr(settings, "backup_public_key", PUBLIC)
    _no_accounts(monkeypatch)
    script = FakeScript()
    monkeypatch.setattr(ob.httpx, "Client", lambda: script.client())

    ran = runner.invoke(cli, ["backup", "run"])
    assert ran.exit_code == 0, ran.output
    assert "Uploaded ardoise-" in ran.output and "(1 database(s))" in ran.output

    status = runner.invoke(cli, ["backup", "status"])
    assert "Configured:   yes" in status.output and "never" not in status.output

    archive, key = tmp_path / "copy.tar.gz.age", tmp_path / "key.txt"
    archive.write_bytes(base64.b64decode(script.received[0]["data"]))
    key.write_text(PRIVATE + "\n")
    restored = runner.invoke(
        cli,
        ["backup", "restore", str(archive), "--key-file", str(key), "--to", str(tmp_path / "r")],
    )
    assert restored.exit_code == 0, restored.output
    assert (tmp_path / "r" / "central.db").exists()


def test_cli_run_and_restore_report_failures(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", databases[0])
    monkeypatch.setattr(settings, "backup_url", "https://script.test/exec")
    monkeypatch.setattr(settings, "backup_secret", "wrong")
    monkeypatch.setattr(settings, "backup_public_key", PUBLIC)
    _no_accounts(monkeypatch)
    monkeypatch.setattr(
        ob.httpx, "Client", lambda: FakeScript({"ok": False, "error": "forbidden"}).client()
    )
    ran = runner.invoke(cli, ["backup", "run"])
    assert ran.exit_code == 1 and "forbidden" in ran.output
    assert "Last error" in runner.invoke(cli, ["backup", "status"]).output

    archive, key = tmp_path / "copy.age", tmp_path / "key.txt"
    archive.write_bytes(b"not an age file")
    key.write_text(PRIVATE)
    restored = runner.invoke(cli, ["backup", "restore", str(archive), "--key-file", str(key)])
    assert restored.exit_code == 1 and "could not decrypt" in restored.output


def _no_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """No teacher accounts: the central database alone, and no real account database read."""
    monkeypatch.setattr("app.cli.backup.central_session", nullcontext)
    monkeypatch.setattr(
        "app.cli.backup.AuthService", lambda session: SimpleNamespace(list_users=lambda: [])
    )


def test_cli_run_names_a_database_it_had_to_leave_out(
    databases: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", databases[0])
    monkeypatch.setattr(settings, "backup_url", "https://script.test/exec")
    monkeypatch.setattr(settings, "backup_secret", "s3cret")
    monkeypatch.setattr(settings, "backup_public_key", PUBLIC)
    monkeypatch.setattr("app.cli.backup.central_session", nullcontext)
    monkeypatch.setattr(
        "app.cli.backup.AuthService",
        lambda session: SimpleNamespace(list_users=lambda: [SimpleNamespace(id=9)]),
    )
    monkeypatch.setattr("app.cli.backup.tenant_url", lambda uid: f"sqlite:///{tmp_path}/t-{uid}.db")
    monkeypatch.setattr(ob.httpx, "Client", lambda: FakeScript().client())
    ran = runner.invoke(cli, ["backup", "run"])
    assert ran.exit_code == 0, ran.output
    assert "(1 database(s))" in ran.output and "t-9.db" in ran.output
    assert "Left out" in runner.invoke(cli, ["backup", "status"]).output
