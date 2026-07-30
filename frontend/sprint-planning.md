# Frontend Sprint Planning — Student Pay Tracker

A step-by-step build plan for the SPA. Each sprint is a **shippable, demoable increment** — the app
stays runnable at every boundary. Ordering favors real value early (a usable roster and evidence screen)
before layering on writes, aggregates, and polish.

Read alongside `CLAUDE.md` (architecture + domain rules) and `FRONTEND_HANDOFF.md` (backend contract).

---

## Sprint 0 — Scaffold & API seam ✅ *(done)*

Foundations already in place:

- Vite + React + TypeScript, Tailwind, React Router, ESLint.
- API layer (`src/api/`): generated `schema.d.ts`, friendly `types.ts`, `client.ts` (fetch wrapper +
  `ApiError` + `downloadCsv`), one typed function per route in `endpoints.ts`.
- `useApi` read hook, `formatMoney` (locale-aware), `DriftBadge`, `Layout` nav shell.
- Route **stubs** wired in `App.tsx`: Dashboard, StudentsList, StudentDetail, EnrollStudent, MonthlyReport.
- No auth (open API).
- **i18n in place** (`src/i18n/`): react-i18next, English + French catalogs, `LanguageSwitcher`, locale
  persisted + synced to `<html lang>`. `client.ts` sends `Accept-Language` on every request and `?lang=`
  on CSV downloads; `ApiError` carries the domain-error `code`. Existing UI copy is already keyed.

**State:** builds clean, dev server boots, but every page is a placeholder `<h1>`.

---

## Sprint 1 — UI foundations & shared primitives

**Goal:** the small, reusable pieces every screen needs, so later sprints assemble rather than reinvent.

- `PageHeader` (title + optional actions slot), `Card`/section wrapper, `Table` primitives.
- Standard **async states**: a `LoadingState`, `ErrorState` (renders `ApiError.message`), and `EmptyState`
  so the `useApi` `loading | error | success` union renders consistently everywhere.
- Form primitives: labeled `TextField`, `MoneyField` (string-preserving — no float coercion), `DateField`,
  `MonthField` (`YYYY-MM`), `Select`, and a `SubmitButton` with pending state.
- `formatDate` helper in `src/lib/` alongside `formatMoney`.
- A reusable `useMutation`-style helper (or convention) for writes: pending / error / success, since
  `useApi` is read-only.
- All primitive copy comes from `useTranslation()` — no hardcoded strings. Establish the error-display
  convention: default to the backend's localized `detail`, with an optional `errors.<code>` namespace in
  the catalogs for domain errors that need custom UI copy.

**i18n:** every primitive takes its labels via `t(...)`; add the `common.*` / `errors.*` keys the async and
form states need to **both** `en.json` and `fr.json`.
**Definition of done:** primitives exist with a tiny demo/storybook-style route or manual check; no screen
logic yet. Everything typechecks and lints, and renders correctly in both languages.

---

## Sprint 2 — Students roster *(read)*

**Goal:** the first genuinely useful screen — see every student ranked by how badly they drift.

- `StudentsList`: table of name, status, fee (`formatMoney`), drift (`DriftBadge`).
- Fetch via `listStudents({ sort: "drift_desc" })` — the only supported sort; make it the default.
- Status filter (all / active / inactive) driving the `status` query param.
- Row → link to `/students/:id`.
- Loading / error / empty states from Sprint 1.

**Endpoints:** `GET /students`.
**Domain:** money is a string; drift is the headline metric — make it visually prominent.
**i18n:** column headers, the status filter options, and the localized `status` labels (`status.active` /
`status.inactive`) come from the catalogs — never render the raw `"active"`/`"inactive"` enum.
**Definition of done:** roster renders live backend data, sorts by drift, filters by status, in both languages.

---

## Sprint 3 — Enroll student *(first write flow)*

**Goal:** establish the mutation pattern end-to-end, including validation-error handling.

- `EnrollStudent` form: name, `join_date` (immutable anchor — explain it in helper text), fee (string),
  optional phone.
- Submit via `createStudent`; on success, redirect to the new student's detail page.
- Surface backend errors: **422** (validation array) and domain strings both via `ApiError.message`;
  map field-level 422 entries to inputs where practical.
- Client-side guards mirror the backend (non-blank name, fee ≥ 0) but the server stays the source of truth.

**Endpoints:** `POST /students`.
**Domain:** `fee` sent as a string; `join_date` set once, never editable later.
**i18n:** field labels, helper text, and submit copy from the catalogs. Client-side validation messages are
frontend-owned (localize them); 422 `msg` strings stay English — map them to your own copy or show
field-level catalog messages rather than surfacing the raw English.
**Definition of done:** can enroll a student and land on their (still-stub-ish) detail page, in both languages.

---

## Sprint 4 — Student detail & ledger *(read — the evidence screen)*

**Goal:** the month-by-month truth for one student.

- `StudentDetail` header/summary: name, status, fee, `cumulative_drift`, `next_expected_date`,
  `payments_count`, `total_paid`.
- Ledger table from `getLedger`: cycle #, expected due date, paid date, days late, amount, running drift.
  Render **unpaid cycles as gaps** (`paid_date: null`) distinctly from paid rows; a Status treatment like
  the CSV (`Unpaid` / `On time` / `N days late`).
- "Download ledger CSV" link (`GET /students/{id}/ledger.csv` — plain `<a download>` works, open API).

**Endpoints:** `GET /students/{id}`, `GET /students/{id}/ledger`, `…/ledger.csv`.
**Domain:** unpaid gaps contribute 0 to drift; drift is cumulative and only grows.
**i18n:** summary labels and ledger headers from the catalogs. The on-screen status column
(`Unpaid`/`On time`/`N days late`) is **frontend-owned** — reuse the `drift.*` plural keys; only the
downloaded CSV's status column is localized by the backend (via the `?lang=` `downloadCsv` already sends).
**Definition of done:** detail page shows summary + full ledger with clear paid/late/unpaid rows and a working CSV download, in both languages.

---

## Sprint 5 — Payments, overrides & profile edits *(writes on detail)*

**Goal:** the teacher's daily actions — all mutations that hang off a student.

- **Record payment** modal/form: month picker → `for_month`, paid date, amount. Send **`for_month` XOR
  `cycle_number`** (prefer `for_month`; never both). On success, `reload()` the ledger + summary.
- **Create override** form: new due date + mandatory reason; render existing overrides as a log.
- **Edit contact/fee/status** via `PATCH` — no `join_date` field (422 if sent).
- Handle the specific errors: **409** duplicate payment, **400** invalid override, **422** future date /
  amount ≤ 0 / bad selectors / blank reason.

**Endpoints:** `POST …/payments`, `POST …/overrides`, `PATCH /students/{id}`.
**Domain:** the `for_month` XOR `cycle_number` rule; immutable `join_date`; "left the school" = `status: inactive`, not delete.
**i18n:** form labels, buttons, and success/confirmation copy from the catalogs. For the domain errors
(409/400), show the backend's localized `detail` or map the stable `code` to an `errors.<code>` key —
whichever gives the clearer message; the status `<select>` uses the `status.*` labels.
**Definition of done:** teacher can record a payment, add an override, and edit fee/phone/status, with the ledger updating live and each error surfaced clearly, in both languages.

---

## Sprint 6 — Dashboard *(landing page)*

**Goal:** the big-picture view that opens the app.

- Stat tiles: `total_collected_this_month`, `total_outstanding` (both `formatMoney`).
- Top latecomers list (active, drift-sorted) → links into student detail; `limit` control.
- Becomes the index route with a strong first impression.

**Endpoints:** `GET /dashboard/summary`.
**Domain:** outstanding/latecomers are computed over **active** students only.
**i18n:** stat-tile labels and section headings from the catalogs; money via locale-aware `formatMoney`.
**Definition of done:** dashboard reflects live totals and top latecomers, each linking to detail, in both languages.

---

## Sprint 7 — Monthly report & CSV exports

**Goal:** the reporting/export surface.

- `MonthlyReport`: year + month pickers → `getMonthlyReport`; table of per-student rows (name, status, fee,
  collected, drift, outstanding) with totals.
- "Download CSV" for `GET /reports/monthly.csv`.
- Validate month 1–12 before calling (backend 422s otherwise).

**Endpoints:** `GET /reports/monthly`, `…/monthly.csv`.
**i18n:** table headers and picker labels from the catalogs; render month names with the active locale
(`Intl.DateTimeFormat`). The exported CSV is localized by the backend via `downloadCsv`'s `?lang=`.
**Definition of done:** report renders for a chosen month with matching totals and a working CSV export, in both languages.

---

## Sprint 8 — Historical "as of", polish & release

**Goal:** the cross-cutting finish that makes it feel done.

- **`as_of` control** wired through dashboard, students list, and student detail for historical/demo views
  (e.g. viewing 2023 data); default = today when omitted.
- Consistent empty/loading/error states, responsive layout, keyboard/focus a11y pass.
- 404 route + not-found handling for unknown student ids.
- **Full French pass:** click through every screen in `fr`, confirm no untranslated keys, check date/money
  formatting and pluralized drift text, and verify CSV exports download in French (`?lang=fr`).
- README with run instructions; final `npm run build` + `lint` gate; light manual QA against seeded data.

**Definition of done:** every screen supports "as of", handles missing/edge data gracefully, reads cleanly
in both English and French, and the app is demo-ready end to end.

---

## Dependencies at a glance

```
S0 ✅ → S1 (primitives)
             ├─ S2 (roster) ──┐
             ├─ S3 (enroll)   ├─→ S4 (detail+ledger) → S5 (writes) ─┐
             │                │                                     ├─→ S8 (polish)
             ├─ S6 (dashboard, needs badge+money from S1/S2) ───────┤
             └─ S7 (reports) ─────────────────────────────────────-┘
```

S1 unblocks everything. S2/S3 are independent and can run in parallel after S1. S5 depends on S4 (writes
live on the detail screen). S6 and S7 depend only on the S1 primitives. S8 is the final cross-cutting pass.

## Conventions carried across all sprints

- Reads through `useApi` + `endpoints.ts`; writes call `endpoints.ts` directly then `reload()`.
- Money stays a string end to end — render with `formatMoney`, never do float math.
- **No hardcoded UI strings** — everything visible goes through `useTranslation()`, with keys added to
  **both** `en.json` and `fr.json`. Never render raw enum values (`status`) or English 422 `msg` strings.
- Error display: prefer the backend's localized `detail` (it respects the `Accept-Language` the client
  sends); map the stable `code` to an `errors.<code>` key only when an error needs custom UI copy.
- Locale-format dates and money with the active locale (`Intl.*` / `formatMoney`); use count-based plural
  keys (`_one`/`_other`) for anything that varies by number.
- Regenerate types with `npm run gen:api` whenever the backend schema changes.
```
