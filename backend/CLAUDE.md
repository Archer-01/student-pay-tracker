# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

All eight sprints in `sprint-planning.md` are implemented: the pure drift core
(`app/services/schedule.py`), SQLAlchemy models + Alembic migration, the sync service layer, a
`typer` CLI (`tracker`), the FastAPI read + write API under `/api/v1` (session-gated, see Auth below), monthly/CSV
reports, ops hardening (SQLite pragmas, DB health check, `ardoise db backup`, minimal logging,
Docker), and English/French i18n on API error messages + CSV exports (`app/core/i18n.py`). `uv run pytest` is green with 100% coverage on `app/services` (100% branch on `schedule.py`);
`ruff` and `mypy` are clean. `sprint-planning.md` remains the record of *why* things are shaped this
way; this CLAUDE.md governs how ongoing changes should be made. The invariants and layering rules
below are not "done" — they must keep holding for any future change.

**Planned work lives in `../BACKLOG.md`** (repo root): sprints 9–13 — classes, packs + the pricing
model that replaces `student.fee`, the student profile rework, enrollment periods (leave/return), and
the leavers-with-debt list. Read it before starting anything in those areas; it records the design
decisions and the open questions, and several of its sprints deliberately revise things this file
currently describes as settled (noted inline below).

## What this is

A backend-only payment tracker for a teacher tracking student tuition payments and lateness ("drift") over time. Stack: Python 3.12+, FastAPI (`fastapi[standard]`), SQLite, SQLAlchemy 2.x, Alembic, Pydantic v2, pytest, `uv`.

## Commands

Use the `Justfile`:
```
just test      # uv run pytest
just lint      # uv run ruff check . && uv run mypy app
just run       # uv run fastapi dev app/main.py
just migrate   # uv run alembic upgrade head
just backup    # uv run ardoise db backup
just docker-up # docker compose up --build
```
Run a single test with `uv run pytest path/to/test_file.py::test_name`. Admin tasks — including
**creating the accounts that can sign in** — run via the `ardoise` CLI, which talks to the DB
directly and therefore keeps working when nobody can log in.

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
enforces completeness). The `ardoise` CLI renders in English — it's the dev/admin tool.

Build order matters and is intentional — each layer depends on the previous being correct:

1. **`services/schedule.py`** — pure functions, no DB/async: `generate_expected_due_dates`, `days_late`, `cumulative_drift`, `next_expected_date`. Calendar-month arithmetic must handle month-end edge cases correctly (e.g. Jan 31 + 1 month = Feb 28/29, not Mar 3). This is the highest-value, highest-risk code in the repo.
2. **Persistence** — SQLAlchemy models for `Student`, `Payment`, `AnchorOverride` + Alembic migrations + thin repos (`StudentRepo`, `PaymentRepo`, `OverrideRepo`) with no business logic (date math must never leak into `app/models` or `app/repos`).
3. **Service layer** — wires domain logic to persistence: `student_service`, `payment_service` (computes `cycle_number`/`days_late` on payment recording), `ledger_service` (full cycle-by-cycle view including unpaid gaps), `override_service`.
4. **CLI** (`typer`) — built *before* the API so the service layer can be hand-tested with real data; doubles as a permanent admin tool.
5. **REST API** — read endpoints first, then write endpoints + auth. The CLI and API must produce identical results for the same operations.
6. **Reports/exports**, then **hardening/ops** (logging, rate limiting, SQLite pragmas, backups, Docker).

## A trap this codebase sets for itself

Repos and services expose a method named **`list`** (`StudentRepo.list`, `ClassService.list`,
`PackService.list`). Inside a class body that name shadows the builtin for **every annotation
declared after it**, so a later `-> list[Thing]` resolves to the method and fails — at import time
with `TypeError: 'function' object is not subscriptable`, or under mypy with `"list" is not valid as
a type`. It has bitten three times. The fix used throughout is a module-scope alias next to the
class (`RosterRows = list[RosterRow]`, `Packs = list[Pack]`), which is order-independent and works
for both mypy and the runtime. Reordering methods "fixes" it only until the next one is added.

## Auth (BACKLOG §5, shipped)

Sign-in is a **gate, not a permission system**: both accounts can do everything. Each account's
data is private, enforced by giving each one **its own database file** — see "Per-teacher
databases" below. The pieces:

- `user` (username, display_name, password_hash, is_active) + `auth_session` (opaque token PK,
  user_id, expires_at). Migration `0008`. There is deliberately **no `role` column** — adding one
  later is a non-rewriting `ALTER TABLE` in SQLite, so carrying a column nothing reads would cost
  about as much as the migration it saves.
- **argon2id** via `app/core/security.py`. Hashes are PHC strings, so cost parameters travel with
  the hash and `login` re-stretches one written under weaker settings.
- **Server-side sessions in an HttpOnly cookie**, not a JWT: revocable instantly, and the token is
  meaningless outside the table. `SameSite=Lax` + `Secure` (settings-driven; **must be off for
  local http dev**, or the cookie is silently dropped and login appears not to stick).
- **Fixed 7-day expiry, refreshed on login** — never slid forward per request. That keeps the read
  path free of writes, which matters on a single-writer SQLite database. Expired rows are purged
  at login, so there is no cron.
- **Routers are gated wholesale** in `main.py` via `include_router(..., dependencies=GATED)`. Add a
  route to a gated router and it is protected by where it lives, not by remembering to decorate it.
  `health` and `auth` stay open; so does the SPA fallback, which serves the login page itself.
- **No CSRF token, deliberately.** Same-origin SPA, `SameSite=Lax`, and every mutation is a JSON
  `POST`/`PATCH`/`DELETE` via `fetch`. If a route ever mutates on `GET`, or the SPA stops being
  same-origin, that reasoning lapses — revisit it rather than assuming it still holds.
- **Accounts come from `ardoise users add`.** No signup route exists. The CLI bypasses HTTP, so it
  is the break-glass path when the last account is locked out.
- **Failed logins are throttled** (`app/core/throttle.py`): 10 failures per (username, IP) in 15
  minutes → 429 with `Retry-After` for 15 minutes. In memory, not a table — under the attack it
  exists to stop, a row per guess would make the throttle itself the denial of service on a
  single-writer database. Keyed on username **and** IP together so guessing at an account can't
  lock its owner out from elsewhere.
- **The login route hashes in a threadpool** (`run_in_threadpool`). argon2id burns ~25ms of CPU by
  design; left on the event loop in an `async def` route it stalls every concurrent request, which
  measurably turned 30 parallel login attempts into ~400ms latency on `/health`. Sync dependencies
  like `require_session` are already off the loop — FastAPI threadpools those automatically.
- **`/docs`, `/redoc` and `/openapi.json` are gated too** — re-registered in `main.py` after
  disabling the built-ins. They leak no student data, but publishing a map of the API to people who
  can't sign in buys nothing. `ardoise openapi` dumps the same schema with no server and no session,
  which is what `npm run gen:api` uses.
- **Tests: `client` is signed in, `anonymous_client` is not.** That is why the ~20 pre-auth
  integration files needed no edits. `tests/integration/test_api_auth.py` is what actually pins the
  gate, including a check that every mounted router is covered.

## Per-teacher databases

Each account's domain data lives in **its own SQLite file**; `settings.database_url` names only the
central database, which holds `user` and `auth_session`.

```
/data/central.db     accounts
/data/tenant-1.db    one teacher's students, classes, packs, payments, ...
/data/tenant-2.db    the other's
```

Why this rather than an `owner_id` column: the guarantee lands in the filesystem instead of in 21
query sites that must each stay correct forever. A forgotten `WHERE owner_id = ...` cannot leak a
row that is not in the file being queried. It also splits the SQLite write lock, so one teacher
saving a payment no longer blocks the other, and it sidesteps `uq_school_class_level_name` /
`uq_pack_name_level`: both teachers can have a "2BAC / A" class and a "Pack Maths", which under a
shared table would have told the second one their class already exists, naming one they cannot see.

**Nothing in `models/`, `repos/`, or `services/` knows about any of this**, and that is the point.
Routing happens in exactly two places:

- `app/api/deps.py::get_db` - resolves the signed-in user, hands back a session on *their* file.
  Every data route already depended on `get_db`, so they were all scoped without being touched.
- `app/cli.py::_session` - the same job for the CLI, driven by the global `--user` / `ARDOISE_USER`.
  Domain commands **refuse to guess** which teacher; writing a student into the wrong database is
  not a mistake you notice quickly.

`get_auth_db` is the central-database counterpart, used by `/auth/*` and `/health`. The split
exists because `require_session` must resolve *who you are* before there is a tenant file to open -
having `get_db` depend on the user directly is what would otherwise be a circular import.

**One migration chain runs against every database.** Tenant files carry empty `user`/`auth_session`
tables and the central file carries empty domain tables. That waste buys a lot: `alembic upgrade
head` works against any file including one created seconds ago, and there is no second migration
history to drift out of step. Startup migrates the central database and every tenant
(`app/core/provisioning.py`); a tenant that fails is logged and skipped rather than blocking boot
for the other teacher.

**Tests collapse both onto one in-memory database** (`conftest._override_db`), which is why none of
the ~331 existing service call sites needed editing. That collapse also means those tests cannot
observe the separation - `tests/integration/test_tenant_isolation.py` uses real files on disk and is
the file that fails if privacy ever regresses.

## Domain invariants to protect

- **Overrides are audit-log style, not mutations.** `override_service.create_override` writes to `anchor_override` and must never touch `student.join_date` or existing payment rows. An override must not reduce `cumulative_drift` for cycles before the override date — this is the whole point of the design and needs an explicit regression test.
- **`join_date` is immutable via the API.** `PATCH /students/{id}` must reject or ignore `join_date` in the request body. This is critical — the drift model breaks if the anchor date can move.
- **Recorded payments are frozen truth.** `payment.amount`, `expected_due_date`, and `days_late` are
  written once by the service layer and never recomputed — not by a fee change, not by a schema
  change, not by anything in `../BACKLOG.md`.
- **Pricing is current, not historical — and that is a deliberate trade** (sprint 10, migration
  0004). A student pays `custom_price` if set, else their pack's price. Changing a pack's price, or
  moving a student to another pack, therefore changes what they owe for months not yet paid. Don't
  "fix" this by reintroducing snapshots without asking: it was chosen knowingly, in exchange for
  one number per student instead of three. What must *not* change is `payment.amount` — money
  already taken stays frozen, so only the outstanding estimate moves.
- **Money is quoted through `PricingService.price_of`, never by reading `pack.price` at a call
  site.** That is what keeps the `custom_price` override and the "no pack means not billed" rule in
  one place instead of being re-derived (and forgotten) per screen.
- **Duplicate payments are rejected, not overwritten.** Recording a payment for a cycle that already has one raises an explicit error (`DuplicatePaymentError` or similar).
- **A write-off is not a payment.** `debt_writeoff` forgives a departed student's balance; it must
  never appear in collected revenue, in the annual report, or in drift. The shortcut it exists to
  prevent is recording a fake payment to clear the leavers list.
- **Absence suspends, it never rewrites.** An unpaid cycle outside every enrollment period is
  suspended (not owed, no drift). A *paid* cycle is never suspended, and suspension can only stop
  future accrual — it must never reduce drift already recorded. `join_date` stays the anchor
  through any number of leaves and returns; a return that reset the schedule would erase exactly
  the history the drift model exists to keep.
- **Cumulative drift is monotonically non-decreasing** as `as_of` moves forward, always ≥ 0, and is 0 if all payments are on time. These are the `hypothesis` property tests referenced above.

## Explicitly out of scope

Don't smuggle these in even if they seem like natural extensions:
- Attendance tracking (per-session presence). Note the *enrollment periods* planned in
  `../BACKLOG.md` §3.4 are not attendance — they record long spans a student was enrolled, so
  billing can skip months they were away. Resist the slide from one into the other.
- **Self-service signup, email verification, password resets, OAuth/SSO.** Login has landed (see the Auth
  section above) but account *creation* stays a CLI operation — there are two users and no email
  infrastructure, so a signup route would be an attack surface with no corresponding benefit.
- **An `owner_id` column on the domain tables.** Data separation is done with one database per
  teacher, not a shared table filtered by owner — see "Per-teacher databases". An owner column now
  would be a second, redundant mechanism for the same guarantee.
- **Cross-teacher views** (e.g. the deferred commission split between Aymen and Ayoub). The data
  is in separate files, so this is not a query — it needs a deliberate design. Ask first.
- **Revenue sharing / commission between the two teachers.** `draft-backlog.md` sketches a split
  ("20%, ayoub takes 50DH from the pack", "College: 25%"), but the rule was never pinned down and
  the client has explicitly deferred it: the app's job is tracking late students. Don't infer a
  formula from those notes — ask.
- Actually sending WhatsApp messages (API only returns the message text as a string)
- PostgreSQL (SQLite is fine for one teacher and hundreds of students)
- Async service layer (routes are `async def`, but the service layer stays sync — SQLite + sync SQLAlchemy is the intended design)
