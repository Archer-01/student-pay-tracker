# CLAUDE.md — backend

The Ardoise API: FastAPI, SQLite (one file per teacher), SQLAlchemy 2, Alembic, Pydantic v2, a
`typer` CLI (`ardoise`), managed with `uv`. It tracks each student's payments and **drift**:
cumulative days paid late, the number the whole product exists to keep right. Repo-wide rules are
in `../CLAUDE.md`. Why things are shaped the way they are is recorded in `../docs/decisions/`;
`README.md` is the sprint-by-sprint log of what shipped.

## Commands

```
just test      # every test, in parallel, no coverage (~5 s): the everyday loop
just test-unit # tests/unit only: pure functions, no database
just cov       # with coverage: app/ ≥ 95 %, app/services 100 % (what CI runs)
just lint      # ruff format --check, ruff check, mypy (what CI runs)
just run       # uv run fastapi dev app/main.py (port 8000: the developer's own server)
just migrate   # uv run alembic upgrade head
```

`just check` at the repo root runs all of CI. One test: `uv run pytest path/to/test.py::name`.
Admin tasks, **including creating the accounts that can sign in**, go through the `ardoise` CLI,
which talks to the databases directly and so keeps working when nobody can log in.

## Working style

- **TDD**: a failing test first, then the code, then the refactor.
- **Anything touching drift needs `hypothesis` property tests** as well as examples (skill
  `drift-invariants`). The corner cases nobody thinks of up front are the failure mode.
- **Every schema change is an Alembic migration** (skill `new-migration`), verified up and down;
  `alembic check` must stay clean.
- After any change to a response or request schema, the frontend runs `npm run gen:api`.

## Layers

```
app/
  core/      settings, engines and SQLite pragmas, per-teacher routing, security, i18n,
             backups (offsite_backup.py: the nightly encrypted copy, decision 0012)
  models/    SQLAlchemy models: no logic
  repos/     thin CRUD: no business logic, no date math
  services/  the domain (schedule, ledger, payments, pricing, reports, school share…): sync, no
             FastAPI; schedule.py is pure, no DB
  schemas/   Pydantic request/response models, separate from the ORM
  api/       routers, deps, error handlers, the PDFs (pdf_export.py, pdf_documents.py)
  cli/       the `ardoise` admin CLI (decision 0010): accounts, db, lookups
tests/
  unit/        pure functions only (a guard fails any test asking for the database)
  integration/ services, API, CLI, migrations, tenant isolation
  conftest.py  per test, a copy of a DB migrated once per run; cheap argon2; signed-in clients
```

- **Date math lives only in `app/services`.** Never in models or repos, never as a computed
  column or default.
- **The service layer is sync and locale-agnostic**: domain errors carry a stable `code` and
  params, never a sentence; the API layer translates. Services take settings such as the school
  share percent as parameters; only the API reads `settings`.
- **The CLI writes no teacher data** (decision 0010): accounts, operations and read-only
  lookups only. Every rule lives in a service, so no caller can skip it.
- **Trap: a method named `list`** (`StudentRepo.list`, `PackService.list`…) shadows the builtin
  for every annotation after it in the class body, so `-> list[Thing]` breaks at import or under
  mypy. Use a module-level alias (`Packs = list[Pack]`); reordering methods only delays it.

## i18n

User-facing text (API errors, PDFs) is translated by `app/core/i18n.translate`, English and
French, per request from `Accept-Language` or `?lang=`. The CLI speaks English.
`tests/unit/test_i18n.py` enforces the first two rules:

- **French typography**: `\u00a0` (written as the escape) before `: ; ? !` and inside `« »`.
  U+00A0, never U+202F: the PDFs' font has no glyph for it.
- **Plurals in pairs** (`<key>_one` / `<key>_other`, chosen by `count`; French counts 0 as one).
- **Pass values, not strings**: `translate` formats `date` and `Decimal` params for the locale.
  A service calling `.isoformat()` or `f"{x:.2f}"` into an error param bakes in English notation.
  PDFs use `format_day` ("14 nov. 2026") and `pdf_export.money` ("240 DH").

## PDFs

They look like the app (`app/api/pdf_export.py` for the page and its blocks,
`pdf_documents.py` for what each says): A4 portrait so one sent over WhatsApp opens full width on
a phone, the app's fonts bundled in `app/assets/fonts` (digits always from Bricolage), its colours
and status words, "Prof. {name}" and "Page x sur y" on every page. Tests read them with `pypdf`
through `tests/pdf.py`: with embedded fonts the raw bytes hold glyph codes, not text.

## Auth

Sign-in is a **gate, not a permission system**: every account can do everything with its own
data, and each account's data is private because it lives in its own file (below).

- `user` + `auth_session` tables (migration 0008); **no `role` column** on purpose.
- **argon2id** (`app/core/security.py`); login re-stretches a hash made with weaker settings. The
  login route hashes in a threadpool: ~25 ms of CPU on the event loop stalls every request.
- **Server-side sessions in an HttpOnly cookie**, not a JWT: revocable, meaningless outside the
  table. `SameSite=Lax`, `Secure` from settings (**off for local http**, or the cookie is
  silently dropped). Fixed expiry (`SESSION_TTL_DAYS`, 90), refreshed only at login, so reads
  never write; expired rows are purged at login.
- **Routers are gated wholesale** in `main.py` (`include_router(..., dependencies=GATED)`); a new
  route is protected by where it lives. `health`, `auth` and the SPA fallback stay open;
  `/docs`, `/redoc` and `/openapi.json` are gated too (`ardoise openapi` dumps the schema).
  `tests/integration/test_api_auth.py` checks every mounted router is covered.
- **No CSRF token, deliberately**: same-origin SPA, `SameSite=Lax`, every mutation a JSON
  `POST`/`PATCH`/`DELETE`. If a `GET` ever mutates, or the SPA stops being same-origin, revisit.
- **Failed logins are throttled in memory** (`app/core/throttle.py`): 10 per (username, IP) in
  15 minutes → 429 with `Retry-After`. Not a table: under attack, a row per guess would make the
  throttle the denial of service.
- **Accounts come from `ardoise users add`.** No signup, reset or OAuth: there is no email and
  there are two users.
- Tests: `client` is signed in, `anonymous_client` is not.

## Per-teacher databases

`settings.database_url` names the central database (`user`, `auth_session`); each teacher's
domain data lives in its own sibling file (`tenant-<id>.db`). A forgotten `WHERE owner_id` can't
leak a row that isn't in the file, the write lock is split per teacher, and both can have a
"2BAC / A" class.

- **Nothing in `models/`, `repos/` or `services/` knows about it.** Routing happens in two places:
  `app/api/deps.py::get_db` (the signed-in user's file) and `app/cli/_common.py::teacher_session` (`--user` /
  `ARDOISE_USER`; domain commands refuse to guess). `get_auth_db` is the central counterpart.
- **One migration chain for every file**: tenant files carry empty auth tables and the central
  file empty domain tables, so `alembic upgrade head` works on any of them. Startup migrates them
  all (`app/core/provisioning.py`); a tenant that fails is logged and skipped.
- Tests collapse both onto one in-memory database, so only
  `tests/integration/test_tenant_isolation.py` (real files) proves the separation.
- No `owner_id` column, no cross-teacher views without a deliberate design: ask first.

## Domain invariants

These must hold for every change:

- **`join_date` is the immutable anchor.** The API rejects it in a PATCH; a return after a leave
  never resets it.
- **Overrides are an audit log**: `override_service.create_override` writes `anchor_override`,
  never touches `join_date` or payments, and never reduces drift for cycles before its date
  (regression test required).
- **Recorded payments are frozen truth**: `amount`, `expected_due_date` and `days_late` are
  written once by the service and never recomputed. A **correction** (`update_payment`:
  `PATCH /students/{id}/payments/{cycle}`, "Modifier ce paiement") fixes a typed
  amount or paid date; `expected_due_date` never moves, `days_late` is re-derived only when the
  paid date was the mistake. Moving a payment to another month is delete + record.
- **Duplicate payments are rejected**, never overwritten.
- **A payment is positive, has at most two decimals, is never dated in the future, and is at
  most the student's monthly price** (`PricingService.price_of`), all enforced in `PaymentService`; an edit checks only a changed amount.
- **Money is quoted through `PricingService.price_of`**, never `pack.price` at a call site: it
  holds the `custom_price` override and "no pack means not billed".
- **Pricing is current, not historical** (migration 0004), a deliberate trade: changing a price
  changes what is owed for months not yet paid, never money already taken. Don't reintroduce
  snapshots without asking.
- **A pack is one name at one level**; its level is locked once a student has it.
- **Absence suspends, it never rewrites**: an unpaid cycle outside every enrolment period is not
  owed and adds no drift; a paid cycle is never suspended; suspension never reduces drift already
  recorded.
- **Cumulative drift never decreases** as `as_of` moves forward, is always ≥ 0, and is 0 when
  every payment was on time (property tests).
- **A price of 0 that was set is free on purpose** (decision 0011): `PricingService.price_status`
  is "free", never chased or flagged. Only "unset" (no pack, no agreed price) gets the Accueil
  reminder.
- **Punctuality is a reading** (`services/punctuality.py`): the mean of `max(0, days_late)` over
  the last six payments due, rounded half up; it never feeds drift.
- **The school share is a flat percentage of money received** (`services/school_share.py`,
  `SCHOOL_SHARE_PERCENT`, default 25, 0 hides it), on collected figures by paid date, never on
  amounts owed or write-offs. The school's part rounds half-up to the cent. One rate for every
  account and no history, knowingly; ask before extending it.
- **A share handover records cash given to the school** (migration 0010): it snapshots what was
  handed over and when; a later payment for that month shows as "short". Only ended months, never
  a future date, never a month with nothing due, never at 0 %. Never revenue, payment or drift.
  `mark_all` (catching up) marks every ended month still due or short on one date, under the
  same rules, each for its share as it stands, and only if the total still equals the one the
  teacher confirmed (`expected`, else `share_outstanding_changed`); the month under way is never
  touched.
- **A write-off is not a payment**: it never appears in revenue, the annual report or drift.
- **A student's `note` is private** (migration 0009) and never reaches a PDF.

## Out of scope

Don't add these even if they look like natural extensions; ask first:

- Attendance per session (enrolment periods record long absences, nothing finer).
- Signup, email verification, password resets, OAuth/SSO.
- An `owner_id` column, or cross-teacher views.
- Any school-share rule beyond the flat percentage.
- Sending WhatsApp messages (the API returns the text only).
- PostgreSQL, or an async service layer.
