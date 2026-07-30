"""Ops hardening: SQLite pragmas, DB health check, and handled-error logging."""

import logging
from collections.abc import Iterator
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import create_engine, text

import app.core.db  # noqa: F401 - importing registers the connect-time pragma listener
from app.core.db import get_db
from app.main import app as fastapi_app
from app.services.exceptions import StudentNotFoundError


def test_sqlite_pragmas_on_file_db(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    try:
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert conn.execute(text("PRAGMA synchronous")).scalar() == 1  # NORMAL
    finally:
        engine.dispose()


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_health_reports_503_when_db_down(client: AsyncClient) -> None:
    class _BrokenSession:
        def execute(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("db down")

        def close(self) -> None:
            pass

    def _broken_db() -> Iterator[object]:
        yield _BrokenSession()

    fastapi_app.dependency_overrides[get_db] = _broken_db  # overrides the fixture's override
    resp = await client.get("/health")
    assert resp.status_code == 503


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_handled_domain_error_is_logged(monkeypatch: object) -> None:
    # Drive the error handler directly and capture via a dedicated logger swapped into the module,
    # which is immune to cross-test global logging state.
    from starlette.requests import Request

    import app.api.errors as errors_mod

    logging.disable(logging.NOTSET)
    collector = _Collector()
    capture_logger = logging.getLogger("test.capture.app_api")
    capture_logger.handlers = [collector]
    capture_logger.setLevel(logging.WARNING)
    capture_logger.propagate = False
    monkeypatch.setattr(errors_mod, "logger", capture_logger)  # type: ignore[attr-defined]

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/students/999",
            "headers": [],
            "query_string": b"",
        }
    )
    response = errors_mod._handle(request, StudentNotFoundError(999), 404)

    assert response.status_code == 404
    messages = [r.getMessage() for r in collector.records]
    assert any("students/999" in m and "404" in m for m in messages), messages
