# Ardoise — monorepo

One deployable image serving a **FastAPI** API and a **built Vite/React SPA** from the **same origin**
(so there's no CORS and one URL to share). Single-teacher tuition tracker; SQLite, single instance.

```
.
├── backend/     # FastAPI app (app/, alembic, uv.lock, tests, …) — listens on :8000, API under /api/v1
├── frontend/    # Vite + React + TypeScript SPA — calls /api/v1 relatively (same-origin in prod)
├── Dockerfile   # multi-stage: build frontend → build backend → runtime (copies SPA to /app/static)
├── docker-compose.yml
├── .dockerignore
├── docs/decisions/  # why things are the way they are
├── Justfile     # `just check`: everything CI runs
├── .github/     # CI, one job per app
└── .claude/     # Claude Code: shared settings, hooks, skills
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
docker build -t ardoise .
docker run --rm -p 8000:8000 -v ardoise-data:/data ardoise
```

Then: `http://localhost:8000/` (the app), `/health`, `/docs`, `/api/v1/...`. Data persists in the
`ardoise-data` volume mounted at `/data` (`DATABASE_URL=sqlite:////data/app.db`).

## Local dev (two processes)

```bash
# backend
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000
# frontend (proxies to :8000)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## Checks

`just check` at the root runs what CI (`.github/workflows/ci.yml`) runs, one job per app:
backend `ruff format --check`, `ruff check`, mypy, pytest with coverage (all of `app/` ≥ 95 %,
`app/services` 100 %) and migrations on an empty database matching the models; frontend
generated API types up to date (`npm run gen:api` leaves no diff), `tsc`, eslint and Vitest with
coverage (≥ 85 %). Day to day, `just test` in `backend/` (~5 s) and `npm test` in `frontend/`
(~5 s) run every test without coverage. `.pre-commit-config.yaml` holds the same tools as an optional local gate
(`uv tool install pre-commit && pre-commit install`), plus a refusal to commit any database.

Repo-level config lives at the root, one copy for both apps: `.gitignore`, `.github/`,
`.pre-commit-config.yaml`, and `.claude/` (Claude Code's shared settings, hooks and skills;
`.claude/hooks/guard-bash.sh` refuses to stage student data or stop the dev servers on
8000/5173).

## Installing it on a phone

Ardoise installs from the browser like an app: it then opens from its home-screen icon without the
address bar or tabs.

- **iPhone (Safari):** open the site, tap Share, then "Sur l'écran d'accueil" / "Add to Home Screen".
- **Android (Chrome):** open the site, then the ⋮ menu → "Installer l'application" / "Install app"
  (Chrome may also offer it on its own).

The installed app has its own sign-in on iPhone, separate from Safari. Updates arrive with each
deploy. Without a connection it still opens and shows the last data seen on each screen, read
only, with a banner saying how old it is; nothing can be recorded until the connection is back.

## Constraints (do not change)

SQLite, **single instance / single writer**, one uvicorn worker. Migrations run on startup
(`alembic upgrade head`).

The app **requires a sign-in**: every `/api/v1` route except `/auth/*` needs a session cookie, and
`/health` stays open for the healthcheck. There is no signup — create accounts from the CLI:

```bash
uv run ardoise users add aymen --name "Aymen"     # prompts for the password
uv run ardoise users list
```

Set `COOKIE_SECURE=false` for local HTTP dev (a `Secure` cookie is dropped over plain http, which
looks like "login succeeds but never sticks"). Leave it at its default of `true` behind TLS.
Sessions last `SESSION_TTL_DAYS` (90 by default), fixed from the moment you sign in.

**Each account's data is private**, in its own SQLite file next to the central one:

```
/data/central.db     accounts (who can sign in)
/data/tenant-1.db    one teacher's students, classes, packs, payments
/data/tenant-2.db    the other's — a physically separate file
```

Nothing is shared between them, and a teacher's database is created with their account. The CLI
therefore needs to know whose data it is working on:

```bash
uv run ardoise --user aymen students list     # or set ARDOISE_USER
uv run ardoise users list                     # account commands need no --user
uv run ardoise db backup --to backups         # backs up every database
```

Configuration and running in production: `backend/README.md`. Why it runs this way:
`docs/decisions/` (0001, 0003, 0004).
