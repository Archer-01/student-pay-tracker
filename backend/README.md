# Ardoise — Backend

The API behind Ardoise: FastAPI, SQLite (one database file per teacher), SQLAlchemy 2, Alembic,
and the `ardoise` admin CLI. How the code is organised and the rules it keeps are in
[`CLAUDE.md`](CLAUDE.md); why things are the way they are is in
[`../docs/decisions/`](../docs/decisions/).

## Set up and run

Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env               # local defaults, including COOKIE_SECURE=false
just migrate                       # create or upgrade the databases
uv run ardoise users add aymen --name "Aymen"    # an account to sign in with (asks for a password)
just run                           # http://127.0.0.1:8000, with the frontend's dev server proxying to it
```

There is no sign-up screen: accounts only come from `ardoise users add`. Each account gets its
own database file (`tenant-<id>.db`) next to the central one, which holds only accounts and
sessions.

## Commands

```bash
just test       # every test, in parallel, no coverage (~5 s)
just test-unit  # tests/unit only: pure functions, no database
just cov        # with coverage: app/ ≥ 95 %, app/services 100 % (what CI runs)
just lint       # ruff format --check, ruff check, mypy
just run        # fastapi dev on :8000
just migrate    # alembic upgrade head
just backup     # ardoise db backup
```

`just check` at the repo root runs everything CI runs, for both apps.

## The `ardoise` CLI

The admin tool. It talks to the databases directly, so it keeps working when nobody can sign
in. Domain commands need to know which teacher: `--user <username>` or `ARDOISE_USER`.

| Group | For |
|---|---|
| `users` | accounts: `add`, `list`, `passwd`, `deactivate`, `activate` |
| `students`, `classes`, `packs`, `payments`, `overrides`, `debts` | the same data the app edits |
| `db migrate` | bring the central database and every teacher's up to date |
| `db backup [--to DIR]` | a consistent, timestamped copy of every database, safe while running |
| `db reset` | drop and recreate the central database (dev only, needs `ALLOW_DB_RESET=1`) |
| `openapi` | print the API schema (what `npm run gen:api` uses) |

`uv run ardoise <group> --help` lists each group's commands. The CLI is due for a rework
(`../docs/decisions/0008`): use its payment commands with care until then.

## Configuration

Read from the environment, then `.env`. No secrets are needed.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | The central database; teachers' files go beside it. `sqlite:////data/app.db` in Docker. A value exported in the shell overrides `.env`. |
| `COOKIE_SECURE` | `true` | `Secure` flag on the session cookie. `false` **only** for local http, or sign-in silently fails. |
| `SESSION_TTL_DAYS` | `90` | How long a sign-in lasts, from login. |
| `SCHOOL_SHARE_PERCENT` | `25` | The school owner's share of every payment, 0–100 (0 hides it). |
| `DEFAULT_LOCALE` | `en` | Language when a request names none; the app always sends one. |
| `LOG_LEVEL` | `INFO` | Logging level; logs go to stdout. |
| `ARDOISE_USER` | — | CLI only: the teacher to work on. |
| `ALLOW_DB_RESET` | — | CLI only: `1` allows `ardoise db reset`. |

## Running in production

The repo's `Dockerfile` builds one image: the built frontend plus this API, served from the
same origin on port 8000. It runs as a non-root user, keeps the databases on the `/data` volume,
and runs `alembic upgrade head` on every start, so a deploy with a new migration needs nothing
by hand. `docker compose up --build` runs the same thing locally.

- **Health**: `GET /health` checks the database (`200`, or `503` when it's unreachable); it is
  open, for the platform's probes.
- **Data**: the `/data` volume is the only copy (`../docs/decisions/0004`). `ardoise db backup`
  makes consistent copies; keep them off the host.
- **Language**: API errors and PDFs follow the request's `Accept-Language` (or `?lang=`), in
  French or English; the CLI speaks English.
