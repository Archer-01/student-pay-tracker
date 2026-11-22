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

The admin tool, for a shell on the server (Northflank) or locally. It does only what the app
can't (`../docs/decisions/0010`): everything the teacher does, from enrolling to payments, is
done in the app. It talks to the databases directly, so it keeps working when nobody can sign
in. Commands about a teacher's data need to know which teacher: `--user <username>` or
`ARDOISE_USER`.

| Command | For |
|---|---|
| `users add / list / passwd / deactivate / activate` | accounts (there is no sign-up in the app) |
| `db migrate` | bring the central database and every teacher's up to date |
| `db backup [--to DIR]` | a plain local copy of every database, on the same disk |
| `backup keygen / run / status / restore` | the nightly encrypted backup to Drive (`../docs/backups.md`) |
| `db reset` | drop and recreate the central database (dev only, needs `ALLOW_DB_RESET=1`) |
| `openapi` | print the API schema (what `npm run gen:api` uses) |
| `students list [--owing] [--search NAME]` | students, most owed first |
| `students show STUDENT` | one student's facts and every month; by id or a piece of the name |
| `students delete STUDENT` | delete a student and their history for good (asks for the name) |
| `debts list` | students who left owing money |
| `share list` | the school's share of each month, and what was handed over |

`uv run ardoise <command> --help` gives the options.

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
| `BACKUP_URL`, `BACKUP_SECRET`, `BACKUP_PUBLIC_KEY` | — | The nightly encrypted backup to Google Drive; all three or none (`../docs/backups.md`). |
| `BACKUP_HOUR` | `3` | When it runs, Morocco time. |
| `ARDOISE_USER` | — | CLI only: the teacher to work on. |
| `ALLOW_DB_RESET` | — | CLI only: `1` allows `ardoise db reset`. |

## Running in production

The repo's `Dockerfile` builds one image: the built frontend plus this API, served from the
same origin on port 8000. It runs as a non-root user, keeps the databases on the `/data` volume,
and runs `alembic upgrade head` on every start, so a deploy with a new migration needs nothing
by hand. `docker compose up --build` runs the same thing locally.

- **Health**: `GET /health` checks the database (`200`, or `503` when it's unreachable); it is
  open, for the platform's probes.
- **Data**: the `/data` volume, backed up every night, encrypted, to the developer's Google Drive
  (`../docs/backups.md`, decision 0012). `/health` reports `"backup": "ok" | "stale" | "off"`.
- **Language**: API errors and PDFs follow the request's `Accept-Language` (or `?lang=`), in
  French or English; the CLI speaks English.
