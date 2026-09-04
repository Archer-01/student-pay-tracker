# Ardoise — monorepo

One deployable image serving a **FastAPI** API and a **built Vite/React SPA** from the **same origin**
(so there's no CORS and one URL to share). Single-teacher tuition tracker; SQLite, single instance.

```
.
├── backend/     # FastAPI app (app/, alembic, uv.lock, tests, …) — listens on :8000, API under /api/v1
├── frontend/    # Vite + React + TypeScript SPA — calls /api/v1 relatively (same-origin in prod)
├── Dockerfile   # multi-stage: build frontend → build backend → runtime (copies SPA to /app/static)
├── docker-compose.yml
└── .dockerignore
```

## How it fits together

- The frontend calls the API with a **relative** base (`/api/v1`, see `frontend/src/api/client.ts`), so in
  production it hits the same origin that serves it — no CORS, no absolute URL.
- In **dev**, `frontend/vite.config.ts` proxies `/api` and `/health` to the backend on `:8000`, so the
  same relative code works locally.
- In **prod**, `backend/app/main.py` mounts the built SPA (`/app/static`) with an SPA fallback **after** all
  API routers, so `/`, hashed `/assets/*`, and hard refreshes on client routes (e.g. `/students`) serve the
  app while `/api/v1/*`, `/health`, `/docs`, `/openapi.json` keep working.

## Build & run (single image)

```bash
docker build -t tracker .
docker run --rm -p 8000:8000 -v tracker-data:/data tracker
```

Then: `http://localhost:8000/` (the app), `/health`, `/docs`, `/api/v1/...`. Data persists in the
`tracker-data` volume mounted at `/data` (`DATABASE_URL=sqlite:////data/app.db`).

## Local dev (two processes)

```bash
# backend
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000
# frontend (proxies to :8000)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## Constraints (do not change)

SQLite, **single instance / single writer**, one uvicorn worker. Migrations run on startup
(`alembic upgrade head`). The app is **open (no auth)** by design — put access control in front of it for
any non-local deployment. See `backend/DEPLOYMENT_BRIEF.md`.
