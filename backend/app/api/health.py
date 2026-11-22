"""Liveness + DB health check (unauthenticated, outside /api/v1).

Probes the **central** database only — it is the one every request needs and the one that
must exist for anybody to sign in. A broken tenant file surfaces at that teacher's login
rather than here, deliberately: one teacher's corrupted database should not make the
orchestrator tear down a container the other teacher is happily using.

`backup` reports the nightly off-site copy (decision 0012) for the developer.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import central_url, get_auth_db
from app.core.offsite_backup import health as backup_health
from app.core.offsite_backup import read_status, status_path
from app.core.settings import settings

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(db: Session = Depends(get_auth_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via a broken-session override in tests
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    # "ok", "partial" (the last copy left a database out), "stale" (no good copy for two days)
    # or "off" (not set up). Information for the
    # developer, never a failure: a restart wouldn't fix a backup, and would interrupt the app.
    backup = backup_health(
        read_status(status_path(central_url())),
        configured=settings.backup_config() is not None,
        now=datetime.now(UTC),
    )
    return {"status": "ok", "database": "ok", "backup": backup}
