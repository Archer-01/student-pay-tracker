# Ardoise — Backend

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
just backup    # ardoise db backup (timestamped SQLite copy)
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
ardoise students add --name "Amina" --join-date 2023-03-05 --fee 300 [--phone …] [--status active]
ardoise students list [--sort-by-drift] [--status active] [--as-of YYYY-MM-DD]
ardoise students show <id> [--as-of YYYY-MM-DD]        # full ledger + cumulative drift
ardoise students delete <id> [--yes]                   # cascades to payments/overrides; prompts unless --yes
ardoise payments record <id> --date YYYY-MM-DD --amount 300 (--for-month YYYY-MM | --cycle N)
ardoise overrides create <id> --new-date YYYY-MM-DD --reason "agreed shift"
ardoise db reset --yes                                  # dev only; needs ALLOW_DB_RESET=1
ardoise db seed [--force]                               # dev only; loads deterministic dummy data
```

`ardoise db seed` populates a fixed, realistic dev dataset (6 students — on-time payers, a chronic
late payer, an unpaid-cycle gap, one anchor override, an inactive student, and one with no phone).
It's deterministic (reproducible) and defined in `app/core/seed.py`; it refuses to run on a
non-empty database unless you pass `--force`.

- **Recording a payment always names the month it settles** — either `--for-month 2024-04` (resolved
  to the right cycle, override-aware) or `--cycle N` (the index shown by `students show`). Exactly one
  is required. This is how prepayments and catching up on old months are expressed.
- Reads compute drift **as of today** unless `--as-of` is given; `--sort-by-drift` puts chronic
  latecomers first. Output is `rich` tables.
- Set `DATABASE_URL` (or `.env`) and run `just migrate` before first use, then `uv run ardoise …`
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
| `GET /api/v1/students/{id}/ledger.pdf` | A student's full ledger as PDF, headed by their name (and phone, when on file) and a human status column |

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
- **Backups** — `ardoise db backup [--to DIR]` writes a timestamped, consistent copy via SQLite's
  online-backup API (safe while the app runs). Cron example (daily 02:00):
  ```cron
  0 2 * * * cd /path/to/app && DATABASE_URL=sqlite:///./app.db /path/to/.venv/bin/ardoise db backup --to /path/to/backups
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

## Sprint 9 — Classes

Students can now be grouped into **classes** (a school level + a name, e.g. *2BAC — Groupe A*).
A class is **organisational only**: it never affects the anchor, payments, or drift. There are
regression tests asserting exactly that — moving a student between classes, or removing them from
one, leaves `cumulative_drift` and the whole ledger byte-identical.

**Levels** are a shared enum (`ClassLevel` in `app/models/school_class.py`): `1AC`, `2AC`, `3AC`,
`TC`, `1BAC`, `2BAC`, declared in **school order**. That order is load-bearing — sorting the stored
values alphabetically would put `1BAC` before `2AC`. The same enum will scope pack prices by level
in sprint 10, which is why it lives in models rather than in the class module alone.

**Schema** (migration `0002`): a `school_class` table (`level` + `name`, unique together, non-blank
name enforced by a CHECK) and a nullable `student.class_id`. Existing students land unassigned, so
no drift or arrears figure moves.

**Endpoints**

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/classes` | `?level=`, `?as_of=`; each item carries `student_count` and class-wide `cumulative_drift`. Returned in school order, then by name |
| `POST` | `/api/v1/classes` | `{level, name}` → 201. Duplicate `(level, name)` → 409 `duplicate_class` |
| `GET` | `/api/v1/classes/{id}` | Detail + counts. Unknown → 404 `class_not_found` |
| `PATCH` | `/api/v1/classes/{id}` | `{level?, name?}`; unknown fields → 422 |
| `DELETE` | `/api/v1/classes/{id}` | 204, or **409 `class_not_empty`** if it still has students |
| `GET` | `/api/v1/classes/{id}/roster.pdf` | Localized roster (`?as_of=`, `?lang=`) |
| `GET` | `/api/v1/students?class_id=` | New filter; students also gained `class_id` + nested `school_class` |

A class's roster is deliberately **not** embedded in the detail response — it's
`GET /students?class_id=`, so there is one representation of "a list of students" in the API and
the roster inherits the status/sort filters for free.

**CLI**

```bash
ardoise classes add --level 2BAC --name "Groupe A"
ardoise classes list [--level 2BAC] [--as-of YYYY-MM-DD]   # school order, counts, class drift
ardoise classes show 1                                     # roster with drift + months overdue
ardoise classes rename 1 --name "Groupe B" [--level 1BAC]
ardoise classes delete 1 --yes                             # refuses a non-empty class
ardoise students add ... --class-id 1
ardoise students assign-class 1 --class-id 2               # or --none to unassign
```

**Note on migration 0002.** Autogenerate produced a `batch_alter_table` on `student`, which on
SQLite rebuilds the table (`DROP TABLE student` + rename). With `PRAGMA foreign_keys=ON` — which
`app/core/db.py` sets on every connection — that drop **fails** against any database that already
holds `payment` or `anchor_override` rows. It passes on an empty database, so the blank-DB test in
the `new-migration` skill could not catch it; it was found by running the upgrade against a copy of
a populated `app.db`. The migration instead adds the column with an inline `REFERENCES` clause,
which SQLite does in place. Verify data migrations against populated copies, not just blank ones.

## Sprint 10 — Packs & the pricing model

What a student pays now comes from a **pack** rather than a bare fee. A pack is a named,
**level-scoped** set of subjects with a price — *Maths seul · 2BAC · 150 DH*. There is no separate
"enrollment type" concept: "Maths only", "Maths + Physics" and the full four-subject pack are all
just packs, so adding an offering is a row, not a code change. Prices vary by level, so each
`(name, level)` pair is its own row — 4 offerings x 6 levels = **24 packs**.

### One price per student

`pack.price` is the price. A student who has agreed something different carries a
**`custom_price`** on their own row, with a **`price_note`** saying why:

```
effective price = student.custom_price  if set,  else  student.pack.price,  else nothing
```

Resolved in one place (`app/services/pricing_service.py`), which everything quoting money goes
through — months overdue, amount owed, the monthly report, the dashboard. A student with no pack
and no agreed price simply isn't billed: they show as owing nothing, and the UI nudges to put them
on a pack. That is a legal state, not an error.

`student.fee` is **gone** (migration 0004). Having `pack.price`, an assignment price *and* a legacy
fee was one pricing concept too many; the agreed price replaces all of it.

### Prices are current, not historical

This is the deliberate trade. Changing a pack's price changes what its students owe for months
they have **not yet paid**, and moving a student to a different pack reprices their unpaid past
months too. There is no price history and no per-month pricing.

Recorded payments are unaffected: `payment.amount` is frozen at insert, so money already taken is
never rewritten — only the outstanding *estimate* moves. Both halves are pinned by tests in
`tests/integration/test_pricing.py`.

An agreed price shields that student from pack price changes, since it is their own number.

### Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/packs` | `?level=`, `?active=`; includes subjects and student count |
| `GET` | `/api/v1/packs/grid` | The offerings x levels matrix. A cell with a null `pack_id` isn't offered |
| `POST` | `/api/v1/packs` | One pack (one offering at one level) |
| `POST` | `/api/v1/packs/offerings` | A whole grid row: one pack per priced level, one shared subject set |
| `PATCH` | `/api/v1/packs/offerings/{name}` | Rename / set subjects across **every** level-variant |
| `PATCH` | `/api/v1/packs/{id}` | One grid cell: `price`, `is_active` |
| `DELETE` | `/api/v1/packs/{id}` | 409 `pack_in_use` if any student is on it — deactivate instead |

A student's pack and price are plain fields on the student: `pack_id`, `custom_price` and
`price_note` on `POST /students` and `PATCH /students/{id}`. Students also gained `monthly_price`
(the effective price) and `amount_owed` (money, not just a month count).

**Offering vs. pack.** An offering is a pack `name` shared by its level-variants; since `level`
lives on the pack, the subject set is physically duplicated across them. `PackService` is what stops
them diverging: name and subject edits always apply to *all* variants (`update_offering`), never one
row, and a test asserts same-named packs always have identical subject sets.

**Level mismatch is advisory.** Assigning a 1AC student a 2BAC pack succeeds and returns a
`level_warning`. A repeating student, or one sitting with a higher group, is a real case — refusing
it would be wrong.

### CLI

```bash
ardoise packs grid                     # the price matrix — fastest way to check a price round
ardoise packs add --name "Maths seul" --level 2BAC --price 150 --subject Maths
ardoise packs list [--level 2BAC]
ardoise packs deactivate 6
ardoise students set-pack 1 --pack-id 6 [--price 90 --price-note "remise fratrie"]
ardoise students set-pack 1 --clear-price   # back to the pack price
ardoise students set-pack 1 --none          # off any pack
```

## Sprint 11 — Student profile & reworked PDFs

**`name` is now `first_name` + `last_name`** (migration 0005), plus `is_repeating` ("redoublant")
and a derived `first_payment_date`. `last_name` is **nullable**: a compound given name with no
family name is a real case, and the seed contains one — "Fatima Zahra". That is also why the
migration splits names with an **explicit mapping** rather than on whitespace, which would have
invented the surname "Zahra". Names that the mapping doesn't know fall back to first-token/rest;
the fallback exists so the migration can't fail, not because it's right — review the table after
upgrading a database this migration hasn't seen.

`Student.full_name` assembles the two parts, so exports, filenames and the CLI all render a name
identically. `first_payment_date` is **derived** (`min(paid_date)`), never stored, so correcting a
payment can't desync it — and it is deliberately not `join_date`; the gap between them is
informative.

`GET /students?q=` searches either name part. The list is ordered by surname.

### The PDF exports were rebuilt

All three (ledger, class roster, monthly report) now share one document shell in
`app/api/pdf_export.py`: a title block, a strip of **headline figures**, a **detail block** of
label/value pairs, the table, and a footer recording when it was generated and as of when. The
ledger previously carried only a name and a phone number; it now shows class, pack, monthly price,
total paid, months overdue, amount owed, drift, phone, status, repeating, student-since, first
payment, and any agreed price with its reason.

Two things worth keeping:

- Tables are sized to **fill the page width**, weighted by each column's widest cell. Left to
  itself reportlab sizes to content and centres it, which leaves a narrow table floating in the
  middle of a landscape page.
- An empty export renders a **sentence** ("No billing cycles have fallen due yet.") rather than a
  lone header row.

`tests/integration/test_api_profile.py` decodes the generated PDFs (ASCII85 + Flate) and asserts on
the text, so the exports are covered rather than eyeballed.

### CLI

```bash
ardoise students add --first-name Amina --last-name Benali --join-date 2023-03-05 [--repeating]
ardoise students list [--search benali]     # † marks a repeating student
```

## Annual revenue

`GET /reports/annual?year=` (and `.pdf`) answers "how much came in this year", month by month.
**All twelve months are always returned**, including empty ones, so a caller can chart or tabulate
a year without filling gaps. Money is counted by the date it was **paid**, not the cycle it
settled — the question is what was taken, not what was owed for it.

The monthly average is over the months that **actually earned**, not over twelve: a year that only
ran from September would otherwise look like it took a third of what it did.

Editing an offering's name or subjects is exposed as `ardoise packs edit-offering <name>
[--rename NEW] [--subject S ...]`, applying across every level at once — per-level edits are
deliberately impossible, since only prices may differ between an offering's variants.

## Sprint 12 — Enrollment periods: leave & return

A student who stops attending in March and comes back in October shouldn't be billed for the
months between — but must not have their history quietly reset either. `enrollment_period` records
the spans a student was actually present:

```
enrollment_period(student_id, entry_date, leave_date NULL, leave_reason)
```

**`join_date` still never moves.** The schedule is generated from the anchor forever; periods say
when the student was *present*, and absence is applied as a filter on top. That separation is the
whole point: a student who leaves owing three months and returns still owes three months, and
keeps the drift they had accrued. `schedule.py` is untouched by this sprint.

### Suspension

An unpaid cycle whose due date falls **outside every period** is `suspended`: rendered as "Away",
excluded from `months_overdue` and `amount_owed`, and unable to accrue drift. Two rules keep it
honest:

- **A paid cycle is never suspended.** A recorded payment is audit truth regardless of what the
  attendance history says — settling a month you were away for still counts, and still counts late.
- **Suspension only removes future accrual.** It cannot subtract drift that already happened,
  because drift comes from recorded payments.

An *open-ended* absence suspends too, not just a closed gap: a student who left and hasn't
returned stops accruing arrears from their departure onward.

### Invariants, and where each is enforced

| Rule | Enforced by |
| --- | --- |
| `leave_date >= entry_date` | CHECK constraint |
| At most one open period per student | **partial unique index** on the open rows |
| Periods never overlap and stay ordered | `EnrollmentService` (+ tests) |
| The first period starts on `join_date` | `EnrollmentService.amend` refuses to move it |

`amend` validates the *proposed* timeline before writing anything — mutating first would let
SQLAlchemy autoflush the bad row and surface a database `IntegrityError` instead of a domain
error, and would leave a rejected amendment sitting dirty in the session.

### Property tests

Four, in `tests/integration/test_enrollment_properties.py` (integration, not unit, because
suspension lives in the ledger and needs a database):

1. Drift is non-decreasing in `as_of` for any set of non-overlapping absences.
2. Recording an absence can only *reduce* arrears — never increase them — and leaves drift alone.
3. A student who never left produces a ledger with nothing suspended: the strict no-op that
   protects every earlier sprint.
4. Leaving and returning the same day is indistinguishable from never leaving.

### Endpoints and CLI

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/students/{id}/periods` | Attendance history, oldest first |
| `POST` | `/api/v1/students/{id}/leave` | `{leave_date, reason?}` |
| `POST` | `/api/v1/students/{id}/return` | `{entry_date}`. **Never blocked by debt** — re-admitting someone who owes is the teacher's call |
| `PATCH` | `/api/v1/students/{id}/periods/{pid}` | Correct a mistyped date |

```bash
ardoise students leave 4 --on 2023-09-30 --reason "Pause"
ardoise students return 4 --on 2024-01-15
ardoise students periods 4
```

Migration 0006 is additive and moves no figure: every existing student gets one **open** period at
their join date, so nothing is suspended. Students already marked `inactive` keep that status but
have **no recorded leave date** — the migration deliberately doesn't invent one, since guessing a
departure month silently changes what they owe. Record a real departure to stop their billing at
the right month.

## Sprint 13 — Leavers with debt

When a student leaves, they drop out of the active list and their unpaid balance goes with them.
This makes that balance visible.

**The flag is derived, never stored:** no open enrollment period, plus an outstanding balance as
of their last departure. A stored boolean would go stale the moment a payment landed; a derived
one clears itself. Sprint 12's suspension does the arithmetic — months after the departure are
suspended, so leaving *caps* the debt at what was owed on the way out instead of letting it grow
forever.

Two routes off the list, and no silent third:

* **They pay.** Recording the payments drops the balance to zero and the flag resolves itself.
* **The teacher forgives it.** `debt_writeoff` records the amount and a mandatory reason,
  append-only in the `AnchorOverride` style. It is **not a payment** — a test asserts writing off
  leaves collected revenue and drift untouched, because the tempting shortcut (recording a fake
  payment to clear the list) would quietly inflate the revenue reports.

**Nothing blocks.** Re-admitting someone who owes is the teacher's call; `POST /return` succeeds
and returns `debt_warning` with the amount. The other loophole — re-enrolling under a fresh record
— is covered by `GET /debts/matches`, which the enrolment form calls as you type. It warns, never
refuses: real people share names.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/debts` | Leavers who owe, largest first, plus the total |
| `GET` | `/api/v1/debts/matches` | Past leavers matching a phone or name (accent/case-insensitive) |
| `GET` | `/api/v1/debts/{student_id}` | One student's status |
| `POST` | `/api/v1/debts/{student_id}/write-off` | `{reason}`; 409 if nothing is owed |

A separate router rather than `/students/...` so the collection route can't be swallowed by
`/students/{student_id}` — FastAPI would try to parse "debts" as an int.

```bash
ardoise debts list
ardoise debts write-off 5 --reason "Déménagement définitif"
```

The dashboard gained a tile, kept separate from `total_outstanding`: chasing someone who has
already left is a different conversation from chasing someone still attending.

**Assumption worth confirming (backlog §6 Q6):** a month counts as owed if its due date fell on or
before the leave date. A student who leaves on the 3rd therefore owes that month.

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
not be blank") stay English; the frontend should validate/localize its own forms. The `ardoise` CLI
is English (dev/admin tool). Every catalog key has both `en` and `fr` (a test enforces this).
