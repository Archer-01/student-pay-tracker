"""Timestamped SQLite backups via the stdlib online-backup API (safe under WAL)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url


def backup_database(source_url: str, dest_dir: Path) -> Path:
    """Copy the file-based SQLite DB at ``source_url`` into ``dest_dir`` as a timestamped file.

    The source filename is folded into the destination (``backup-20260912-ardoise.db``) because
    there is no longer one database to back up: the central account store and each teacher's data
    are separate files, and a name built from the timestamp alone would have them overwrite each
    other inside the same second.

    Returns the backup path. Raises ``ValueError`` for non-SQLite / in-memory / missing sources.
    """
    url = make_url(source_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("backup only supports a file-based SQLite database")

    source = Path(url.database)
    if not source.exists():
        raise ValueError(f"source database does not exist: {source}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"backup-{stamp}-{source.stem}.db"

    src_conn = sqlite3.connect(source)
    try:
        dst_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dst_conn)  # online backup — consistent even with the app running
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return dest
