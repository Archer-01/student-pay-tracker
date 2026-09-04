from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import classes, dashboard, debts, health, packs, reports, students
from app.api.errors import register_error_handlers
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="Ardoise",
    description="Backend for tracking student tuition payments and lateness (drift).",
    version="0.1.0",
)

register_error_handlers(app)

# Single-teacher tool: the API is open (no auth). Run it on a trusted host/network.
app.include_router(health.router)
app.include_router(students.router, prefix="/api/v1")
app.include_router(classes.router, prefix="/api/v1")
app.include_router(packs.router, prefix="/api/v1")
app.include_router(debts.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")

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
        SPA shell."""
        if full_path.startswith("api/") or full_path in {"health", "docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404)
        candidate = FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")
