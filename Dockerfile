# syntax=docker/dockerfile:1
#
# One image serving the built Vite SPA + the FastAPI API from the same origin (no CORS).
# Build context is the monorepo root; sources live under backend/ and frontend/.

# --- Stage 1: build the frontend ----------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /fe
# Deps first (cached layer), then the sources.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /fe/dist (VITE_API_BASE_URL unset -> relative /api/v1 calls)

# --- Stage 2: install backend deps + the project with uv ----------------------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
# Dependencies first (cached layer), then the project itself.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ .
RUN uv sync --frozen --no-dev

# --- Stage 3: runtime — slim, non-root, persistent /data volume ---------------
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
# The built SPA, where app/main.py's FRONTEND_DIR expects it (/app/static).
COPY --from=frontend --chown=appuser:appuser /fe/dist /app/static
ENV PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL="sqlite:////data/app.db"
USER appuser
EXPOSE 8000
# One worker (single SQLite writer). Apply migrations, then serve the API + SPA.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
