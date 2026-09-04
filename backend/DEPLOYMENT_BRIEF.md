# Deployment Brief — Ardoise (backend)

For an agent recommending **how/where to deploy** this backend. It states the app's shape, the hard
constraints that rule deployment choices in or out, what's already provided, and the open questions to
resolve. It does **not** prescribe a platform — that's your call after reading.

---

## 1. TL;DR

A tiny Python **FastAPI + SQLite** API for **one teacher** tracking ~20–30 students' tuition payments.
Traffic is a handful of requests per day. Two facts dominate every deployment decision:

1. **It's a single-node, single-writer SQLite app.** The database is one file on disk. Deploy **one
   instance** with a **persistent volume**. Do **not** run multiple replicas/nodes (they'd each get a
   separate DB file, or corrupt a shared one). No load balancer fan-out, no autoscaling.
2. **The API has no authentication** (intentionally removed — single trusted user). Anyone who can
   reach it can read/write real student PII. **Access control must be provided by the infrastructure**
   (private network, VPN/tunnel, IP allowlist, or an auth proxy at the edge). Do not expose it openly
   on the public internet as-is.

Everything else is easy: it's small, container-ready, and cheap to run (a $5 VPS or a Raspberry Pi is
plenty).

---

## 2. Runtime facts

- **Language/stack:** Python **3.12**, FastAPI (ASGI) served by **uvicorn**, SQLAlchemy 2.x, Alembic,
  Pydantic v2. Dependency/lock tooling: **uv** (`uv.lock` committed). Build backend: hatchling.
- **Service layer is synchronous** (sync SQLAlchemy on SQLite). Routes are `async def` but call sync
  code — fine at this scale. **Run a single worker** (or very few); it's one SQLite file on one host.
- **Listens on HTTP `:8000`** (no TLS itself — terminate TLS at a proxy/platform).
- **Start command** (what the container already does):
  `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`
  — migrations run on startup and are idempotent.
- **Health check:** `GET /health` runs a real `SELECT 1` → `200 {"status":"ok","database":"ok"}` or
  **503** if the DB is unreachable. Unauthenticated. Use it for platform/orchestrator health probes.
- **Endpoints:** everything under `/api/v1` (students, payments, overrides, dashboard, reports, CSV
  exports) + `/health`, `/docs`, `/openapi.json`.

## 3. Hard constraints (these decide the platform)

- **Persistent disk required.** The SQLite file must survive restarts and redeploys. Platforms with an
  **ephemeral filesystem and no attachable volume** (vanilla AWS Lambda, Google Cloud Run without a
  mounted volume, Vercel/Netlify functions) are a **poor fit** unless paired with continuous
  replication (see Litestream in §6).
- **Exactly one instance / one writer.** Never scale to 2+ replicas against the same volume. Keep it to
  a single container/process with the volume attached.
- **Migrations on deploy.** `alembic upgrade head` before serving (already wired into the container
  CMD). Safe to run every start.
- **WAL mode is on** (`journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON` set per connection).
  Fine on a normal filesystem; **avoid networked filesystems** (NFS/some overlay mounts) that don't
  handle SQLite locking well — use a real block/persistent disk.

## 4. Configuration (environment variables)

Config is read from env first, then `.env` (pydantic-settings; unknown keys are ignored). **No secrets
required.**

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | SQLite URL. In Docker it's `sqlite:////data/app.db` (absolute, on the volume). |
| `DEFAULT_LOCALE` | `en` | Fallback language (`en`/`fr`) when a request sets none. |
| `LOG_LEVEL` | `INFO` | Stdlib logging level. Logs go to stdout/stderr. |

> Heads-up: a `DATABASE_URL` exported in the shell **overrides** `.env`. On the deploy host make sure it
> points at the intended SQLite path (the container sets it correctly).

## 5. Security posture (read carefully)

- **No auth in the app.** This is deliberate for a single-teacher tool. For any non-local deployment,
  put access control in front of it — e.g. a reverse proxy with Basic auth, an identity proxy
  (Cloudflare Access / Tailscale / Authelia), an IP allowlist, or keep it on a private network / VPN.
- **Data is PII** — student names, phone numbers, fees, payment history. Treat backups and access
  accordingly; prefer HTTPS end-to-end and a non-public surface.
- **TLS:** the app speaks plain HTTP; put it behind a proxy/platform that provides HTTPS.
- **CORS is not configured in the app.** If the frontend is served from a **different origin**, either
  (a) serve the frontend same-origin (reverse-proxy both under one domain — simplest), or (b) ask the
  backend team to add `CORSMiddleware` for the frontend's origin. A separate **frontend** (SPA) consumes
  this API; coordinate origins/CORS as part of the deploy.

## 6. Persistence & backups

- **The volume is the source of truth.** If it's lost, the data is gone. Pick a platform whose volume is
  durable, and/or replicate.
- **Built-in backup:** `ardoise db backup --to <dir>` writes a timestamped, consistent copy via SQLite's
  online-backup API (safe while running). Schedule it (cron / platform scheduled job) and, ideally, ship
  copies **off the host** (object storage). Example cron in the README.
- **Stronger option worth considering:** **Litestream** (continuous SQLite replication to S3-compatible
  storage) gives near-continuous, off-host durability and point-in-time restore — a good fit for a
  single-node SQLite app, and it makes otherwise-ephemeral platforms viable.

## 7. Resource footprint

Minimal. ~**256–512 MB RAM**, a fraction of a shared CPU, and a few MB of disk (30 students' data is
tiny; leave headroom for WAL + backups). The cheapest tier of essentially any provider works; it will
happily run on a Raspberry Pi.

## 8. What's already provided (container-ready)

- **`Dockerfile`** — multi-stage (uv, `--frozen`), **non-root** user, `ENV PATH` includes the venv,
  creates `/data`, `EXPOSE 8000`, and the migrate-then-serve `CMD`. Default `DATABASE_URL` points at
  `/data/app.db`.
- **`docker-compose.yml`** — one `api` service on `:8000`, a **named volume `tracker-data:/data`** for
  the DB, a `/health` healthcheck, `restart: unless-stopped`. (No secrets/env needed beyond the defaults.)
- **`.dockerignore`**, health check, and logging are all in place.

So the simplest path is: build the image and run the single container with a persistent volume + a TLS/
access layer in front. (Note: this environment has no Docker daemon, so the image hasn't been built
here — build/run on the target.)

## 9. Candidate options (weigh these — not a recommendation)

All must satisfy §3 (single instance + persistent volume + a non-public/authenticated surface):

- **Small VPS + Docker Compose + Caddy/Traefik** (DigitalOcean/Hetzner/Linode): full control, trivial
  persistent disk, easy TLS + Basic-auth/allowlist at the proxy. Closest to the project's original
  "cheap VPS / Raspberry Pi" intent. Most predictable.
- **Fly.io**: first-class **volumes**, cheap single-machine apps, plays well with **Litestream**. Good
  fit; ensure you run **one** machine for the volume.
- **Render / Railway**: managed containers with **persistent disks** (paid tier). Simple; confirm the
  disk is durable and the service is a single instance.
- **Raspberry Pi / on-prem at the school**: matches the "trusted network" design; keeps PII local.
  Needs a tunnel (Tailscale/Cloudflare Tunnel) for remote access, and a backup destination.
- **Poor fits without extra work:** Cloud Run / Lambda / serverless functions (ephemeral FS, no single
  persistent writer) — only viable with Litestream + object storage, which adds complexity.

## 10. Open questions for you (the deploying agent) to resolve

1. **Exposure:** public internet, private/VPN, or LAN-only? This drives the access-control layer (§5).
2. **Where does the frontend live** and on what origin/domain? Same-origin (reverse proxy) vs cross-
   origin (needs CORS added). The frontend is a separate app consuming this API.
3. **Who needs remote access** (just the teacher? the developer?) and from where — informs VPN/tunnel vs
   public + auth-proxy.
4. **Backup destination & retention** — on-volume only is fragile; prefer off-host (object storage) or
   Litestream. What's acceptable RPO?
5. **Budget / ops appetite** — hands-on VPS vs managed PaaS.
6. **Region/data residency** — PII of (likely Moroccan) students; any locality preference?

## 11. Repo pointers

- `README.md` — full feature/endpoint reference (sprint-by-sprint), Docker + backup + i18n sections.
- `CLAUDE.md` — architecture, invariants, out-of-scope (note: **no auth, SQLite only, single writer**).
- `FRONTEND_HANDOFF.md` — the frontend contract (auth-free API, `Accept-Language`/`?lang`, CORS caveat).
- `Dockerfile` / `docker-compose.yml` — the deployment artifacts described above.
- `app/core/settings.py` — the exact config surface.
