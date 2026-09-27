"""Liveness + DB health check (unauthenticated, outside /api/v1).

Probes the **central** database only — it is the one every request needs and the one that
must exist for anybody to sign in. A broken tenant file surfaces at that teacher's login
rather than here, deliberately: one teacher's corrupted database should not make the
orchestrator tear down a container the other teacher is happily using.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_auth_db

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(db: Session = Depends(get_auth_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via a broken-session override in tests
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    return {"status": "ok", "database": "ok"}
