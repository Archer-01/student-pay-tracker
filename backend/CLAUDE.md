# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

All eight sprints in `sprint-planning.md` are implemented: the pure drift core
(`app/services/schedule.py`), SQLAlchemy models + Alembic migration, the sync service layer, a
`typer` CLI (`tracker`), the FastAPI read + write API under `/api/v1` (open, no auth), monthly/CSV
reports, ops hardening (SQLite pragmas, DB health check, `tracker db backup`, minimal logging,
Docker), and English/French i18n on API error messages + CSV exports (`app/core/i18n.py`). `uv run pytest` is green with 100% coverage on `app/services` (100% branch on `schedule.py`);
`ruff` and `mypy` are clean. `sprint-planning.md` remains the record of *why* things are shaped this
way; this CLAUDE.md governs how ongoing changes should be made. The invariants and layering rules
below are not "done" — they must keep holding for any future change.

## What this is

A backend-only payment tracker for a teacher tracking student tuition payments and lateness ("drift") over time. Stack: Python 3.12+, FastAPI (`fastapi[standard]`), SQLite, SQLAlchemy 2.x, Alembic, Pydantic v2, pytest, `uv`.

## Commands

Use the `Justfile`:
```
just test      # uv run pytest
just lint      # uv run ruff check . && uv run mypy app
just run       # uv run fastapi dev app/main.py
just migrate   # uv run alembic upgrade head
just backup    # uv run tracker db backup
just docker-up # docker compose up --build
```
Run a single test with `uv run pytest path/to/test_file.py::test_name`. The API is open (no auth);
admin tasks also run via the `tracker` CLI, which talks to the DB directly.

Definition of done for any sprint: tests green, `ruff check` clean, `mypy app` clean, README updated with what shipped, git tag `sprint-N`.

## Working style

- **TDD, no exceptions:** write a failing test, then the minimal code to pass, then refactor. No production code without a red test first.
- **Migrations from day one.** Don't skip Alembic even for early schema changes — SQLite makes schema changes feel free, but they aren't.
- **The drift calculation is the core domain logic and the entire value of this product.** Any change touching it needs property-based tests (`hypothesis`) in addition to example tests — the failure modes are the corner cases nobody thinks of up front. Don't cut these tests under time pressure even though other sprints (7, half of 8) are droppable.

## Architecture (as built)

```
app/
  core/          # settings, db session/engine + SQLite pragmas, backup, logging, i18n (en/fr)
  models/        # SQLAlchemy models (Student, Payment, AnchorOverride) — no logic
  repos/         # thin CRUD repositories — no business logic, no date math
  schemas/       # Pydantic v2 request/response schemas (separate from the ORM)
  services/      # domain logic (drift, ledger, dashboard, reports) — no DB in schedule.py, no FastAPI
  api/           # FastAPI routers (students, dashboard, reports, health), deps (locale), error handlers
  cli.py         # typer CLI, installed as `tracker`
  main.py        # FastAPI app wiring
tests/
  unit/          # pure schedule.py tests (example + hypothesis)
  integration/   # DB/service/API/CLI/ops tests
  conftest.py    # fresh migration-applied in-memory DB per test; authed httpx client fixtures
alembic/
Dockerfile · docker-compose.yml   # ops packaging
```

**i18n stays at the edges.** User-facing text (API error messages, CSV headers/labels) is localized
via `app/core/i18n.translate` (English/French; locale chosen per request by `Accept-Language` or
`?lang`, default from `settings.default_locale`). The **service layer is locale-agnostic**: domain
exceptions carry a stable `code` + params (never a formatted sentence), and the API handler / CSV
endpoints translate. Every new user-facing string gets both `en` and `fr` in the catalog (a test
enforces completeness). The `tracker` CLI renders in English — it's the dev/admin tool.

Build order matters and is intentional — each layer depends on the previous being correct:

1. **`services/schedule.py`** — pure functions, no DB/async: `generate_expected_due_dates`, `days_late`, `cumulative_drift`, `next_expected_date`. Calendar-month arithmetic must handle month-end edge cases correctly (e.g. Jan 31 + 1 month = Feb 28/29, not Mar 3). This is the highest-value, highest-risk code in the repo.
2. **Persistence** — SQLAlchemy models for `Student`, `Payment`, `AnchorOverride` + Alembic migrations + thin repos (`StudentRepo`, `PaymentRepo`, `OverrideRepo`) with no business logic (date math must never leak into `app/models` or `app/repos`).
3. **Service layer** — wires domain logic to persistence: `student_service`, `payment_service` (computes `cycle_number`/`days_late` on payment recording), `ledger_service` (full cycle-by-cycle view including unpaid gaps), `override_service`.
4. **CLI** (`typer`) — built *before* the API so the service layer can be hand-tested with real data; doubles as a permanent admin tool.
5. **REST API** — read endpoints first, then write endpoints + auth. The CLI and API must produce identical results for the same operations.
6. **Reports/exports**, then **hardening/ops** (logging, rate limiting, SQLite pragmas, backups, Docker).

## Domain invariants to protect

- **Overrides are audit-log style, not mutations.** `override_service.create_override` writes to `anchor_override` and must never touch `student.join_date` or existing payment rows. An override must not reduce `cumulative_drift` for cycles before the override date — this is the whole point of the design and needs an explicit regression test.
- **`join_date` is immutable via the API.** `PATCH /students/{id}` must reject or ignore `join_date` in the request body. This is critical — the drift model breaks if the anchor date can move.
- **Duplicate payments are rejected, not overwritten.** Recording a payment for a cycle that already has one raises an explicit error (`DuplicatePaymentError` or similar).
- **Cumulative drift is monotonically non-decreasing** as `as_of` moves forward, always ≥ 0, and is 0 if all payments are on time. These are the `hypothesis` property tests referenced above.

## Explicitly out of scope

Don't smuggle these in even if they seem like natural extensions:
- Attendance tracking
- Auth of any kind — the API is intentionally open (single trusted teacher on a trusted network). No token, no users, no multi-teacher.
- Actually sending WhatsApp messages (API only returns the message text as a string)
- PostgreSQL (SQLite is fine for one teacher and hundreds of students)
- Async service layer (routes are `async def`, but the service layer stays sync — SQLite + sync SQLAlchemy is the intended design)
