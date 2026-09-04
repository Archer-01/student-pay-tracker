# Payment Tracking App — Backend Sprint Planning

**Stack:** Python 3.12+ · FastAPI · SQLite · SQLAlchemy 2.x · Alembic · Pydantic v2 · pytest · uv
**Scope:** Backend only. Frontend is a later concern.
**Working style:** Solo dev, TDD-first, small vertical slices. Each sprint ends with something runnable and tested.

---

## Ground rules (apply to every sprint)

- **TDD loop:** write the failing test → write the minimal code to pass → refactor. No production code without a red test first.
- **Definition of done for a sprint:** all tests green, `uv run pytest` clean, `uv run ruff check` clean, `uv run mypy app` clean, a README section documenting what shipped and how to run it, and a git tag `sprint-N`.
- **Don't skip Alembic even in Sprint 1.** SQLite makes schema changes feel free — they aren't. You will change the schema. Migrations from day one.
- **The drift calculation is the core domain logic.** Every sprint that touches it needs property-based tests (`hypothesis`) in addition to example-based tests, because the failure modes are precisely the corner cases you don't think of.

---

## Sprint 0 — Project scaffolding (½ day)

Not really a sprint. Setup only. Skip if you have a template you like.

**Deliverables**
- `uv init`, dependency groups: `main` (fastapi, sqlalchemy, alembic, pydantic-settings), `dev` (pytest, pytest-asyncio, pytest-cov, hypothesis, httpx, ruff, mypy)
- Repo layout:
  ```
  app/
    core/          # settings, db session, security
    models/        # SQLAlchemy models
    schemas/       # Pydantic schemas
    services/      # domain logic (drift, cycle generation)
    api/           # FastAPI routers
    main.py
  tests/
    unit/
    integration/
    conftest.py
  alembic/
  ```
- `pyproject.toml` with ruff + mypy config (strict on `app/services`, lenient elsewhere)
- `.env.example`, `Makefile` or `justfile` with `test`, `lint`, `run`, `migrate`
- Pre-commit hook: ruff format, ruff check, mypy on staged files
- `pytest.ini` with async mode, coverage threshold 85% on `app/services`
- Empty CI-ready `pytest` run passes

**Exit criteria:** `uv run pytest` runs (zero tests, zero failures), `uv run uvicorn app.main:app` serves `GET /health`.

---

## Sprint 1 — Domain core: drift calculation, pure functions (2–3 days)

**This is the highest-value sprint.** Get the math right before anything touches a database. Every subsequent sprint depends on this being correct.

**Build (in test-first order):**
- `services/schedule.py`
  - `generate_expected_due_dates(join_date, up_to)` → list of due dates from anchor, using calendar-month arithmetic (Jan 31 + 1 month = Feb 28/29, not Mar 3 — this is a real bug you will hit)
  - `days_late(expected, paid)` → int, negative if early, zero if on time
  - `cumulative_drift(join_date, payments, as_of)` → int, sum of `max(0, days_late)` across all cycles due on or before `as_of`
  - `next_expected_date(join_date, as_of)` → next unpaid due date
- No DB, no FastAPI, no async. Plain functions on plain dataclasses/Pydantic models.

**Tests (write first):**
- Example tests for the March 5 → April 10 → May 10 → June 10 scenario from the scoping doc. Cumulative drift after June 10 must equal 15.
- Month-end edge cases: Jan 31, Feb 29 leap year, Mar 31 → Apr 30, DST-adjacent dates (use `date` not `datetime` to sidestep this, but test it).
- Property tests with `hypothesis`:
  - Cumulative drift is monotonically non-decreasing as `as_of` moves forward
  - Cumulative drift ≥ 0 always
  - If all payments are on their expected date, drift is 0
  - Adding a payment can never decrease drift (only clearing an override can)
- Sprint acceptance test: reproduce the scoping doc's Table 3 exactly.

**Exit criteria:** 100% branch coverage on `services/schedule.py`. If a property test finds a bug, add the failing case as an example test and fix it.

---

## Sprint 2 — Persistence layer: models + migrations (2 days)

**Build:**
- SQLAlchemy 2.x models for `Student`, `Payment`, `AnchorOverride` matching the scoping doc's data model
- Explicit constraints: `Student.join_date` NOT NULL, `Payment.days_late` computed column or set-on-insert (prefer a service-layer calculation that writes it, so it's testable), `AnchorOverride.reason` NOT NULL and non-empty via CHECK constraint
- Alembic init + first migration `001_initial_schema`
- Repository pattern: `StudentRepo`, `PaymentRepo`, `OverrideRepo` — thin wrappers, no business logic
- Session factory with proper scoping for tests (transactional rollback fixture)

**Tests (write first):**
- Model tests: uniqueness, NOT NULL, CHECK constraints all raise `IntegrityError` when violated
- Repo tests against a real SQLite (in-memory for speed): create, get, list, delete, bulk operations
- Migration test: apply migration to empty DB, assert schema matches; downgrade, assert clean
- `conftest.py` fixture: fresh in-memory DB per test with all migrations applied — this fixture is used from now on for every integration test

**Exit criteria:** `alembic upgrade head` on a blank DB creates every table; `alembic downgrade base` cleans it up; repo tests pass; no business logic has leaked into the repo layer (grep for date math in `app/models` or `app/repos` — should find nothing).

---

## Sprint 3 — Service layer: wire domain logic to persistence (2 days)

**Build:**
- `services/student_service.py`: enroll, get, list, update contact/fee, change status
- `services/payment_service.py`: `record_payment(student_id, paid_date, amount)` — this is where the drift math from Sprint 1 meets the DB. Computes `cycle_number` and `expected_due_date` from the student's anchor, computes `days_late`, writes the row.
- `services/ledger_service.py`: `get_ledger(student_id, as_of)` returns the full cycle-by-cycle view including gaps (unpaid cycles show as `paid_date=None`, `days_late=None`)
- `services/override_service.py`: `create_override(student_id, new_due_date, reason)` — writes to `anchor_override`, **does not touch `student.join_date` or existing payment rows** (test this explicitly)

**Tests (write first):**
- Integration tests for each service using the DB fixture
- **Critical regression test:** an override does not reduce `cumulative_drift` for cycles before the override date. Write this test before writing override logic — it's the whole point of the audit-log design.
- Recording a payment for a cycle that already has one: must raise `DuplicatePaymentError` (or your chosen exception), not silently overwrite
- Ledger correctness across a 12-cycle scenario with mixed on-time, late, and skipped payments

**Exit criteria:** you can drive the full March→June scenario through the service layer via a pytest test and get the expected drift number. No API yet.

---

## Sprint 4 — CLI (1–2 days)

**Why before the API:** a CLI is the fastest way to hand-test the service layer with real data, and it doubles as an admin tool forever. FastAPI comes next, not now.

**Build:**
- `app/cli.py` using `typer`
- Commands:
  - `students add --name --phone --join-date --fee`
  - `students list [--sort-by-drift]`
  - `students show <id>` (prints the ledger + cumulative drift)
  - `payments record <student-id> --date --amount`
  - `overrides create <student-id> --new-date --reason`
  - `db reset` (dev only, gated by env var)
- Entry point wired via `pyproject.toml` so `uv run ardoise students list` works

**Tests:**
- CLI tests using typer's `CliRunner`, hitting a temp SQLite file
- One end-to-end test: enroll student, record 4 payments with drift, `students show` output contains "15" (cumulative drift)

**Exit criteria:** you can seed a realistic 20-student dataset from the CLI and inspect it. **Do this**. Real data will surface bugs no test caught. Fix them, add tests, tag the sprint.

---

## Sprint 5 — REST API: read endpoints (1–2 days)

**Build:**
- FastAPI routers under `/api/v1`
- Endpoints (all read-only this sprint):
  - `GET /students` — list, supports `?sort=drift_desc`, `?status=active`
  - `GET /students/{id}` — student + summary
  - `GET /students/{id}/ledger` — cycle-by-cycle
  - `GET /students/{id}/drift` — just the cumulative number, cheap endpoint for dashboards
  - `GET /dashboard/summary` — total collected this month, total outstanding, top-N chronic latecomers
- Pydantic v2 response schemas separate from ORM models
- Consistent error handling (custom exception → HTTP mapping via exception handlers)
- OpenAPI docs auto-generated, tags per resource

**Tests (write first):**
- `httpx.AsyncClient` against the app for each endpoint
- Status codes, response shape, sorting, filtering
- 404 on unknown student, 422 on bad query params
- One integration test that seeds via service layer and asserts the dashboard summary math is right

**Exit criteria:** `/docs` renders, curl works for every endpoint, tests green.

---

## Sprint 6 — REST API: write endpoints + auth (2 days)

**Build:**
- Endpoints:
  - `POST /students`
  - `PATCH /students/{id}` (contact, fee, status — never `join_date`, enforce this)
  - `POST /students/{id}/payments`
  - `POST /students/{id}/overrides`
- **Auth:** HTTP Basic or a static bearer token from env var (`TEACHER_API_TOKEN`). One user. Middleware or FastAPI dependency, applied to all `/api/v1/*` routes except `/health`.
- Request validation: fees > 0, dates not in the future for `paid_date`, reasons non-empty for overrides
- Idempotency consideration for `POST /payments` — decide now: (a) reject duplicates, or (b) accept an idempotency key header. Recommend (a) for v1.

**Tests (write first):**
- Auth: 401 without token, 401 with wrong token, 200 with correct token — for every write endpoint and one read endpoint (spot check)
- **Regression test:** `PATCH /students/{id}` with `join_date` in the body is rejected (either 422 or silently ignored — pick one and test it). This is critical; the whole design falls apart if `join_date` becomes mutable through the API.
- Full happy-path integration test: create student → record 4 payments → verify drift via GET
- Validation error tests for every field constraint

**Exit criteria:** the CLI and the API give identical results for the same operations. Add a test that proves this for at least one flow.

---

## Sprint 7 — Reports & exports (1–2 days)

**Build:**
- `GET /reports/monthly?year=&month=` — JSON: total collected, outstanding, per-student status
- `GET /students/{id}/ledger.csv` — CSV export of a student's ledger, for the "evidence" use case in the scoping doc
- `GET /reports/monthly.csv` — same as JSON version but CSV
- Streaming responses for CSV (don't buffer in memory)

**Tests:**
- CSV header + row correctness, encoding (UTF-8 with BOM if Excel-on-Windows is a target — probably yes for the teacher)
- Report totals equal sum of per-student amounts (invariant test)

**Exit criteria:** teacher can be handed a CSV file that clearly shows a chronic-latecomer's history. Actually generate one from seeded data and eyeball it.

---

## Sprint 8 — Hardening & ops (1–2 days)

Not glamorous. Do it anyway before the frontend, because you'll be running this thing on some cheap VPS or a Raspberry Pi.

**Build:**
- Structured logging (`structlog` or stdlib with JSON formatter), correlation IDs per request
- Rate limiting on write endpoints (`slowapi`) — cheap protection against a fat finger
- SQLite pragmas: `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL` (application-level, on connect)
- Backup script: `sqlite3 .backup` to timestamped file, cron-friendly, documented in README
- Dockerfile (multi-stage, `uv sync --frozen`, non-root user)
- `docker-compose.yml` for local run with a mounted volume for the DB
- Health check that actually checks the DB, not just returns 200

**Tests:**
- Startup smoke test: app boots, DB pragmas are set (query `PRAGMA foreign_keys` and assert)
- Backup script test: run it, restore into a new DB, verify row counts match

**Exit criteria:** you can `docker compose up` on a fresh machine and have a working, persistent, backed-up backend.

---

## What's deliberately not in these sprints

- **Attendance tracking** — scoping doc explicitly punted this. Don't smuggle it in.
- **Multi-user / multi-teacher** — single-user auth is enough for v1. Adding a `users` table later is a two-migration change.
- **WhatsApp integration** — the scoping doc labels this "nice-to-have, not urgent." Build the API to return the message text as a string; sending is the frontend's or a later worker's problem.
- **PostgreSQL** — SQLite is fine for one teacher and hundreds of students. If you migrate, the SQLAlchemy models won't change; only the connection string and a couple of Alembic tweaks.
- **Async everywhere** — FastAPI is async, use `async def` in routes. But your service layer can stay sync; SQLite with sync SQLAlchemy is simpler and faster for this workload. Don't add `asyncpg`-style complexity to a single-writer SQLite app.

---

## Realistic total

**~12–17 working days** for a solo dev with TDD discipline. Sprints 1–3 are the ones you don't rush; they contain the actual product. Sprints 4–8 are plumbing.

If you find yourself under time pressure, the sprints you can cut without regret are 7 (reports — move CSV to on-demand endpoints later) and half of 8 (skip Docker, keep the logging and backups). Cutting Sprint 1's property tests to save time is a mistake — that's where the leaks the teacher is losing money to actually live.
