from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, classes, dashboard, debts, health, packs, reports, students
from app.api.deps import require_session
from app.api.errors import register_error_handlers
from app.core.logging import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Bring every database to head before serving.

    The central one first — it has to exist before it can be asked who the teachers are — then one
    per account. A teacher's database is created when their account is, so this loop is not what
    creates them; it is what applies a *new* migration to all of them on the next deploy.

    A tenant that fails to migrate does not stop startup: the other teacher is unaffected and
    should still be able to work. See `migrate_all`.
    """
    from sqlalchemy import select

    from app.core.db import central_url, get_auth_db
    from app.core.provisioning import migrate, migrate_all
    from app.models import User

    migrate(central_url())

    session = next(get_auth_db())
    try:
        user_ids = list(session.scalars(select(User.id)))
    finally:
        session.close()

    migrate_all(user_ids)
    yield

# The built-in docs URLs are disabled here and re-registered below behind the session gate. An
# open /openapi.json hands an attacker a complete map of the API; it leaks no student data, but
# there is no reason to publish it to people who cannot sign in.
app = FastAPI(
    title="Ardoise",
    description="Backend for tracking student tuition payments and lateness (drift).",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

register_error_handlers(app)

# Every data router is gated at the router level rather than per endpoint: a new route added to
# any of these is protected because of where it lives, not because someone remembered to decorate
# it. Accounts are provisioned with `ardoise users add` — there is no signup route.
#
# Two routers stay open, deliberately:
#   - health: the Docker healthcheck has no session and must not need one.
#   - auth:   login can't require a login; /logout should work with a stale cookie; and /me is
#             how the SPA finds out whether to show the login page (it 401s on its own, via
#             require_session, rather than by being gated here).
GATED = [Depends(require_session)]

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(students.router, prefix="/api/v1", dependencies=GATED)
app.include_router(classes.router, prefix="/api/v1", dependencies=GATED)
app.include_router(packs.router, prefix="/api/v1", dependencies=GATED)
app.include_router(debts.router, prefix="/api/v1", dependencies=GATED)
app.include_router(dashboard.router, prefix="/api/v1", dependencies=GATED)
app.include_router(reports.router, prefix="/api/v1", dependencies=GATED)

# --- Docs, behind the same gate as the data -----------------------------------
# `ardoise openapi` dumps the same schema from the CLI without a server or a session, which is
# what `npm run gen:api` uses — so gating these costs the frontend workflow nothing.


@app.get("/openapi.json", include_in_schema=False, dependencies=GATED)
async def openapi_schema() -> JSONResponse:
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False, dependencies=GATED)
async def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} — API")


@app.get("/redoc", include_in_schema=False, dependencies=GATED)
async def redoc() -> HTMLResponse:
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} — API")


# --- Serve the built frontend (single-origin: no CORS) ------------------------
# The Dockerfile copies the Vite build output here (app/main.py -> parent.parent == repo root ==
# /app in the image, so this resolves to /app/static). When absent (e.g. a pure-API run), this
# block is skipped and only the API is served. Registered LAST so it never shadows the API / docs
# routes above.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "static"

if FRONTEND_DIR.is_dir():
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """SPA fallback: serve a real static file if it exists, else index.html (so a hard refresh
        on a client-side route like /students returns the app, not a 404). API/docs paths are
        matched above; guard here so an unknown /api or /health GET returns 404 rather than the
        SPA shell.

        Deliberately **not** gated: this serves the login page itself, so requiring a session here
        would make signing in impossible. It hands out the app shell, never any data — every
        figure the shell renders comes from a gated /api/v1 call."""
        if full_path.startswith("api/") or full_path in {"health", "docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404)
        candidate = FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")
