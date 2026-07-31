# Student Pay Tracker — Backend

Backend for a payment tracker a teacher uses to track student tuition payments and lateness ("drift") over time. See `sprint-planning.md` for the full build plan and `CLAUDE.md` for architecture/working-style notes.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
cp .env.example .env   # then fill in DATABASE_URL if you don't want the sqlite default
```

## Commands

```bash
just test      # run tests
just lint      # ruff check + mypy
just run       # start the dev server (fastapi dev)
just migrate   # apply Alembic migrations
just backup    # tracker db backup (timestamped SQLite copy)
just docker-up # docker compose up --build
```

- **`tracker …`** — the admin CLI (installed by `uv sync`); talks to the DB directly.
- **The API is open — no auth.** Every endpoint is reachable without a token; run it on a trusted
  host/network (it's a single-teacher tool). See the Sprint 6 note.

> This README is organized as a sprint-by-sprint log (all 8 sprints are complete). Read top-to-bottom
> for the full picture, or jump to a sprint for a specific area.

## Sprint 0 — Project scaffolding

Shipped:
- Repo layout (`app/{core,models,schemas,services,api}`, `tests/{unit,integration}`, `alembic/`)
- `app/main.py` FastAPI app with `GET /health`
- Ruff + mypy configured in `pyproject.toml` (strict typing on `app/services`)
- Alembic initialized, `DATABASE_URL` read from `app/core/settings.py` (falls back to `sqlite:///./app.db`)
- `pytest.ini` (async mode, 85% coverage threshold on `app/services`)
- `Justfile` and `.pre-commit-config.yaml`

Run it:
```bash
uv sync
just migrate
just run
curl localhost:8000/health
```

## Sprint 1 — Drift domain core

The heart of the product: pure, database-free functions in `app/services/schedule.py` that
compute when tuition is *due* and how much cumulative lateness ("drift") a student has accrued.

**The model**

- Each student is anchored to a `join_date`. The due schedule is fixed: `join_date` is cycle 0
  (the enrollment month) and cycle *n* is due *n* calendar months later.
- Calendar-month arithmetic **preserves the anchor day and clamps** to the target month's length —
  `Jan 31 → Feb 28` (or `Feb 29` in a leap year), while `Jan 31 + 2 months → Mar 31` (the 31 is
  preserved, never permanently drifted to 28).
- Actual payments are free-form (early, late, mid-month, prepaid, back-paid). Each `Payment` names
  the `cycle_number` it settles, so prepayment and back-payment are represented exactly rather than
  guessed from the paid date. A real payment covering several months is one `Payment` per cycle
  sharing a `paid_date`.
- Lateness is day-based (no grace period): `days_late = paid − expected`. Drift sums
  `max(0, days_late)` over every cycle due on or before `as_of`, so early/prepaid payments add 0,
  unpaid cycles add nothing, and drift is monotonically non-decreasing as time advances.
- All arithmetic uses `datetime.date` (never `datetime`), so DST and timezones cannot affect it.

**Functions** — `generate_expected_due_dates`, `days_late`, `cumulative_drift`, `next_expected_date`
(plus the `add_months` helper and the `Payment` dataclass).

**Tests** — example/edge cases in `tests/unit/test_schedule.py` (canonical scenario, month-end &
leap-year clamping, DST-adjacent dates, prepay/back-pay/unpaid) and `hypothesis` property tests in
`tests/unit/test_schedule_properties.py` (drift monotonic, always ≥ 0, zero when all on time, never
decreases when a payment is added). 100% branch coverage on `schedule.py`.

```bash
just test   # 34 tests, 100% branch coverage on app/services/schedule.py
just lint   # ruff + mypy (strict) clean
```

## Sprint 2 — Persistence layer

Where the domain gets stored: SQLAlchemy 2.x models, the first Alembic migration, and thin
repositories. All date arithmetic stays in `app/services` — models and repos hold no business logic.

**Schema** (`app/models/`, migration `alembic/versions/0001_initial_schema.py`)

- **`student`** — `name`, `phone`, `join_date` (the immutable anchor), `fee` (`Numeric(10,2)`,
  `CHECK fee >= 0` so free/scholarship/discounted students are allowed), `status`
  (`active`/`inactive`), `created_at`.
- **`payment`** — `student_id`, `cycle_number`, `paid_date`, `expected_due_date`, `days_late`
  (all set by the service layer in Sprint 3 — never computed in the model), `amount`, `created_at`.
  `UNIQUE(student_id, cycle_number)` backs duplicate-payment rejection; `CHECK amount >= 0`,
  `CHECK cycle_number >= 0`.
- **`anchor_override`** — audit-log rows: `student_id`, `new_due_date`, `reason`
  (`CHECK length(trim(reason)) > 0`), `created_at`.
- Foreign keys use `ON DELETE RESTRICT` (`PRAGMA foreign_keys=ON` on every connection, so it's
  actually enforced): the database never silently orphans or cascade-deletes payment/override history.
  The admin **delete-student** operation (`StudentService.delete`, CLI + API — never exposed in the
  frontend) removes those child rows explicitly in the service layer first, so a student *with*
  history can be deleted, but only through that intentional cascade, not by accident.

**Access** — `app/core/db.py` (declarative `Base`, lazily-built engine, session factory, `get_db`)
and thin repos in `app/repos/` (`StudentRepo`, `PaymentRepo`, `OverrideRepo`): create / get / list /
delete only.

**Tests** — `tests/conftest.py` provides the DB fixture every integration test reuses: a fresh,
migration-applied in-memory SQLite database **per test** (disposed at teardown, so service code that
commits stays isolated). `tests/integration/` covers constraint violations (each raises
`IntegrityError`), repo CRUD, and a migration up/down round-trip.

```bash
just migrate                     # apply migrations (needs DATABASE_URL=sqlite:///./app.db)
uv run alembic downgrade base    # tear the schema back down
```

> **Environment note:** the app reads `DATABASE_URL` from the real environment first, then `.env`.
> If a `DATABASE_URL` is exported in your shell (e.g. left over from another project), it overrides
> the SQLite default in `.env` and `just migrate` / `just run` will target the wrong database. Unset
> it (`unset DATABASE_URL`) or point it at `sqlite:///./app.db`. Tests are unaffected — they build
> their own in-memory database.

## Sprint 3 — Service layer

Where the drift math meets the database. Services (`app/services/`) orchestrate the repos and the
pure schedule functions; each is constructed with a `Session` and commits its own writes.

**Overrides — permanent re-anchor.** `schedule.py` now takes an optional `overrides` (a list of
`new_due_date` values). From an override's month forward the schedule follows the new anchor; earlier
cycles are untouched. Example: join Mar 5 → `Mar5, Apr5, May5, Jun5, Jul20, Aug20, …` after a Jul 20
override (July moves from the 5th to the 20th, no double charge). Multiple overrides in one month
collapse to the last.

**Services**
- `StudentService` — `enroll`, `get`, `list(status=…)`, `update_contact_fee`, `change_status`,
  `delete` (hard-delete, cascading to the student's payments and overrides — admin/dev only).
  There is deliberately **no way to change `join_date`** (the drift anchor is immutable).
- `PaymentService.record_payment(student_id, cycle_number, paid_date, amount)` — computes the cycle's
  override-aware `expected_due_date` and `days_late` and **freezes** them on the row. Recording a
  second payment for the same cycle raises `DuplicatePaymentError`. The cycle is always given
  explicitly (the teacher states which month a payment settles).
- `LedgerService.get_ledger(student_id, as_of)` — the full cycle-by-cycle view; paid cycles show their
  frozen values, unpaid cycles show as gaps (`None`) and add 0 to the running cumulative drift.
  `cumulative_drift(student_id, as_of)` returns the number directly.
- `OverrideService.create_override(student_id, new_due_date, reason)` — validates the date
  (`> join_date`, no backward re-anchor) and a non-empty reason; writes an audit-log row and **never**
  touches `join_date` or existing payment rows.

**Why freezing matters:** because each payment's lateness is frozen at record time and overrides only
affect unpaid/future cycles, **creating an override can never retroactively reduce drift for earlier
cycles** — the core audit-log invariant, covered by a dedicated regression test and a `hypothesis`
property (expected dates before an override's month are provably unchanged).

```bash
just test   # 96 tests; app/services 100% covered, schedule.py 100% branch
just lint   # ruff + mypy (strict on app/services) clean
```

## Sprint 4 — CLI

A `typer` admin CLI over the service layer, installed as the `tracker` command (the project now has
a hatchling build backend, so `uv sync` installs it). The CLI is thin wiring — the same services the
API will use — so CLI and API results match.

```bash
tracker students add --name "Amina" --join-date 2023-03-05 --fee 300 [--phone …] [--status active]
tracker students list [--sort-by-drift] [--status active] [--as-of YYYY-MM-DD]
tracker students show <id> [--as-of YYYY-MM-DD]        # full ledger + cumulative drift
tracker students delete <id> [--yes]                   # cascades to payments/overrides; prompts unless --yes
tracker payments record <id> --date YYYY-MM-DD --amount 300 (--for-month YYYY-MM | --cycle N)
tracker overrides create <id> --new-date YYYY-MM-DD --reason "agreed shift"
tracker db reset --yes                                  # dev only; needs ALLOW_DB_RESET=1
```

- **Recording a payment always names the month it settles** — either `--for-month 2024-04` (resolved
  to the right cycle, override-aware) or `--cycle N` (the index shown by `students show`). Exactly one
  is required. This is how prepayments and catching up on old months are expressed.
- Reads compute drift **as of today** unless `--as-of` is given; `--sort-by-drift` puts chronic
  latecomers first. Output is `rich` tables.
- Set `DATABASE_URL` (or `.env`) and run `just migrate` before first use, then `uv run tracker …`
  (or just `tracker …` inside the venv).

Tests drive the CLI end-to-end with `typer`'s `CliRunner` against a temp database, including the
canonical scenario (enroll → three late payments → `students show` reports drift **15**), proving the
CLI and service layer agree.

## Sprint 5 — REST API (read endpoints)

Read-only FastAPI endpoints under `/api/v1`, backed by the same services as the CLI. Routes are
`async def`; the service layer stays sync. Response schemas are Pydantic v2, separate from the ORM
(money serializes as a JSON string, e.g. `"300.00"`). Every endpoint accepts optional
`?as_of=YYYY-MM-DD` (default today).

| Method & path | Purpose |
|---|---|
| `GET /api/v1/students` | List; `?status=active\|inactive`, `?sort=drift_desc`; each item includes `cumulative_drift` and `months_overdue` |
| `GET /api/v1/students/{id}` | Student + summary (drift, months overdue, next expected date, payments count, total paid) |
| `GET /api/v1/students/{id}/ledger` | Full cycle-by-cycle ledger (unpaid cycles as gaps) |
| `GET /api/v1/students/{id}/drift` | Just the cumulative drift number |
| `GET /api/v1/dashboard/summary` | `?as_of`, `?limit`: collected this month, total outstanding, top-N latecomers |
| `GET /health` | Liveness (outside `/api/v1`) |

- **Dashboard math:** `total_collected_this_month` = payments whose *paid date* is in `as_of`'s month;
  `total_outstanding` = Σ over **active** students of (unpaid cycles due ≤ `as_of`) × fee; latecomers
  are active students with drift > 0, most first.
- Domain errors map to HTTP: unknown student → **404**, other domain errors → **400**; bad query
  params → **422**.

```bash
unset DATABASE_URL          # avoid a stray Postgres URL; use .env's sqlite
just migrate
just run                    # fastapi dev app/main.py  → http://127.0.0.1:8000
open http://127.0.0.1:8000/docs
curl "http://127.0.0.1:8000/api/v1/students"
```

Tests use `httpx.AsyncClient` against the ASGI app (DB dependency overridden to a per-test database):
every endpoint, filtering/sorting, 404/422 paths, the dashboard summary math at a fixed `as_of`, that
`/openapi.json` and `/docs` render, and that the API's drift matches the service layer's.

## Sprint 6 — REST API (write endpoints)

The write endpoints.

> **Auth note:** this sprint originally added a static bearer token (`TEACHER_API_TOKEN`) guarding
> `/api/v1`. It was later **removed** as unnecessary overhead for a single-teacher tool — the API is
> now **open** (no token anywhere). Run it on a trusted host/network.

| Method & path | Body | Notes |
|---|---|---|
| `POST /api/v1/students` | name, join_date, fee (≥0), phone?, status? | → **201** |
| `PATCH /api/v1/students/{id}` | phone?, fee?, status? | → **200**; sending `join_date` (or any unknown field) → **422** |
| `DELETE /api/v1/students/{id}` | — | → **204**; cascades to the student's payments/overrides (admin/dev; not exposed in the frontend) |
| `POST /api/v1/students/{id}/payments` | paid_date, amount (>0), and **exactly one** of `cycle_number` / `for_month` | → **201**; duplicate cycle → **409** |
| `POST /api/v1/students/{id}/overrides` | new_due_date, reason | → **201** |

- **Validation → 422:** negative fee, blank name, non-positive amount, future `paid_date`, blank
  reason, bad/ambiguous month selector. **Domain errors:** duplicate payment → 409, override before
  join date → 400, unknown student → 404.
- `join_date` is immutable through the API (the anchor can never move) — enforced by `extra="forbid"`
  on the update schema and covered by a regression test.

```bash
unset DATABASE_URL && just migrate && just run
curl -X POST http://127.0.0.1:8000/api/v1/students \
  -H "Content-Type: application/json" \
  -d '{"name":"Amina","join_date":"2023-03-05","fee":"300"}'
```

A test proves the **CLI and API produce identical drift** for the same enroll+payment flow.

## Sprint 7 — Reports & exports

Reporting endpoints under `/api/v1`, for the "evidence" use case.

| Method & path | Returns |
|---|---|
| `GET /api/v1/reports/monthly?year=&month=` | JSON: total collected, total outstanding, a row per active student |
| `GET /api/v1/reports/monthly.pdf?year=&month=` | The same, as a downloadable PDF |
| `GET /api/v1/students/{id}/ledger.pdf` | A student's full ledger as PDF, with a human status column |

- **Monthly report** lists active students only; `collected` counts payments by paid-date in that
  month, `outstanding` = unpaid cycles due by month-end × fee, `drift` is as of month-end. Totals are
  the sums of the rows (invariant, tested).
- **Exports are PDF** (`application/pdf`, `Content-Disposition: attachment`) — friendly to open on a
  phone/tablet. The ledger PDF's **Status** column reads `Unpaid` / `On time` / `N days late` — a
  chronic latecomer's history at a glance. Rendered with reportlab's built-in font (Latin + French
  accents); Arabic-script names are not shaped/rendered.

```bash
curl "http://127.0.0.1:8000/api/v1/students/1/ledger.pdf?as_of=2023-07-31" -o ledger.pdf
```

## Sprint 8 — Hardening & ops

Right-sized for a single teacher (~20–30 students): durability, a real health check, backups, minimal
logging, and Docker packaging. No rate limiting or structlog (over-engineering at this scale); no new
dependencies.

- **SQLite pragmas** (applied on every connection): `foreign_keys=ON`, `journal_mode=WAL`,
  `synchronous=NORMAL` — safer, fewer "database is locked" errors.
- **Health check** — `GET /health` runs `SELECT 1` → `{"status":"ok","database":"ok"}`, or **503** if
  the DB is unreachable (good for uptime monitors and the Docker healthcheck). Open (no token).
- **Backups** — `tracker db backup [--to DIR]` writes a timestamped, consistent copy via SQLite's
  online-backup API (safe while the app runs). Cron example (daily 02:00):
  ```cron
  0 2 * * * cd /path/to/app && DATABASE_URL=sqlite:///./app.db /path/to/.venv/bin/tracker db backup --to /path/to/backups
  ```
- **Logging** — minimal stdlib logging (`LOG_LEVEL` env, default INFO); handled domain errors are
  logged with method/path/status.

### Docker

```bash
docker compose up --build          # migrates + serves on :8000, DB persisted in a named volume
curl http://127.0.0.1:8000/health
```

The image is multi-stage (uv, `--frozen`), runs as a **non-root** user, stores the SQLite DB in a
persistent `/data` volume, and has a container healthcheck hitting `/health`. Migrations run on
startup.

## Internationalization (i18n)

The backend speaks **English and French** (`app/core/i18n.py` — a small dependency-free catalog; no
gettext/babel). English is the developer default; French is for the teacher. What's localized:

- **API error messages** — the `detail` string in `4xx` domain errors. Responses also include a stable
  machine **`code`** (e.g. `"student_not_found"`) so a frontend can localize by code if it prefers.
- **PDF exports** — table headers and the ledger's status column (`Impayé` / `À temps` / `En retard de
  N jours`) and the student status label (`Actif`/`Inactif`).

**Choosing the locale** (per request): `Accept-Language: fr` (standard) or `?lang=fr` (explicit, wins
over the header). Falls back to `settings.default_locale` (`DEFAULT_LOCALE` / env `DEFAULT_LOCALE`,
default `en`).

```bash
curl "http://127.0.0.1:8000/api/v1/students/999" -H "Accept-Language: fr"
# {"detail":"Aucun élève avec l'identifiant 999","code":"student_not_found"}
curl "http://127.0.0.1:8000/api/v1/students/1/ledger.pdf?as_of=2023-07-31&lang=fr" -o releve.pdf
```

Design: **the service layer is locale-agnostic** — exceptions carry a `code` + params, and only the
edges (API handler, PDF exports) translate. Pydantic **422 field-format** messages (e.g. "name must
not be blank") stay English; the frontend should validate/localize its own forms. The `tracker` CLI
is English (dev/admin tool). Every catalog key has both `en` and `fr` (a test enforces this).
