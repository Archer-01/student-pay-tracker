# Ardoise — Frontend

A Vite + React + TypeScript SPA for a **single-teacher student tuition tracker**. It talks to a FastAPI
backend that tracks student payments and **"drift"** (cumulative days a student pays late — the app's
headline metric). English + French.

## Screens

- **Dashboard** — collected this month, total outstanding, top latecomers.
- **Students** — roster ranked by drift, filterable by status.
- **Student detail** — summary + month-by-month ledger, with actions to record a payment, add a due-date
  override, edit contact/fee/status, and download the ledger as PDF.
- **Enroll** — add a student.
- **Monthly report** — per-student collected/outstanding for a chosen month, with PDF export.

## Requirements

- Node 20+ and npm.
- The backend running locally at `http://127.0.0.1:8000` (see `FRONTEND_HANDOFF.md`).

## Getting started

```bash
npm install
npm run dev        # → http://localhost:5173
```

## Commands

```bash
npm run dev        # Vite dev server
npm run build      # tsc -b (typecheck) then vite build → dist/
npm run lint       # eslint
npm test           # vitest run (jsdom)
npm run test:watch # vitest, watching
npm run preview    # preview the production build
npm run gen:api    # regenerate src/api/schema.d.ts from the backend's /openapi.json
```

## Backend connection & CORS

The backend has no CORS middleware, so the browser can't call it cross-origin. In dev, Vite **proxies
`/api` → `http://127.0.0.1:8000`** (see `vite.config.ts`) and the API base URL is relative (`/api/v1`), so
requests are same-origin and CORS never applies. Override the base with `VITE_API_BASE_URL` (see
`.env.example`) only if you point the app at the backend directly — in which case the backend must send
CORS headers itself.

## Internationalization

react-i18next with `en` + `fr` catalogs (`src/i18n/locales/`). The active locale is sent as
`Accept-Language` on every request (and `?lang=` on PDF downloads), so backend error messages and PDF
exports come back localized. All UI copy lives in the catalogs — keep both languages in sync.

## Classes

Students can be grouped into classes (`/classes`, `/classes/:id`). A class is a **school level**
(`1AC`, `2AC`, `3AC`, `TC`, `1BAC`, `2BAC`) plus a name, e.g. *2BAC — Groupe A*.

- `src/lib/classes.ts` holds `CLASS_LEVELS` (in **school order** — sorting the level strings
  alphabetically puts `1BAC` before `2AC`) and `classLabel()` for the `"2BAC — Groupe A"` display
  form. The level is not part of the stored name, so the label is composed.
- The class detail page reads twice: `getClass(id)` for the header stats and
  `listStudents({ class_id })` for the roster. The roster is the ordinary students list filtered by
  class, so there's one representation of a student list in the app.
- **"Add student"** on a class page routes to `/students/new?class_id=<id>`. `EnrollStudent` reads
  the query param and pre-selects that class — the field stays **visible and editable**, because
  pre-filling invisibly is how students end up in the wrong class.
- Classes are organisational only. Moving a student between classes never changes their drift; the
  backend has regression tests pinning this, and the UI must not imply otherwise.
- Deleting a class with students returns 409; the page surfaces the backend's localized message
  rather than guessing the reason.

## Packs & pricing

`/packs` renders the price list as a **matrix**: one row per offering, one column per level
(`src/routes/PacksGrid.tsx`). That shape is the point — with 4 offerings x 6 levels, one form per
pack would mean 24 screens for a single round of price changes, and the subject lists of an
offering's level-variants would drift apart.

- **Editing a cell** changes one pack's price (and whether it's offered). **Editing a row** (name,
  subjects) goes through `updateOffering`, which hits every level-variant at once.
- A cell shows its **student count**, and the edit dialog warns how many students a price change
  moves — because it takes effect **immediately**, including for months they haven't paid yet.
- An empty cell means the offering isn't sold at that level. That's legal — don't invent packs.

**A student has one pack and one price.** `PricingFields`
(`src/components/students/PricingFields.tsx`) is shared by the enrolment and edit forms: pick a
pack, and optionally an **agreed price** with a note saying why. Leave the agreed price blank and
they pay the pack price; fill it in only for an arrangement. The student page shows the effective
price and, when there's an arrangement, renders it against the pack's ("200,00 instead of 280,00 ·
remise fratrie") so the exception is visible rather than buried.

A student with no pack isn't billed yet — they show a dash and owe nothing.

## Student profile

A student has `first_name` + `last_name` (the surname is **optional** — a compound given name with
no family name is a real case), `is_repeating`, and a derived `first_payment_date`. Render names
with `full_name`; don't reassemble the parts.

`NameFields` and `PricingFields` (`src/components/students/`) are shared by the enrolment and edit
forms, so a student is described in the same shape wherever you are. The student page shows the
whole profile in one grid, including empty values as "—" — a grid that changes shape per student is
harder to scan. The students list has a search box (`?q=`, matched against either name part) and
marks repeating students.

## Attendance (leave & return)

A student page shows an **Attendance** table once there is more than one period — a single open
period since the join date is already covered by "Student since". The action button flips between
*Mark as left* and *Mark as returned* depending on whether they're currently attending.

In the ledger, a month the student was away is **styled distinctly from an unpaid one** (muted and
italic, status "Away"). Colouring them alike is the mistake to avoid: an away month is not a debt,
and the teacher reads that column to decide who to chase.

Returning is never blocked by an outstanding balance — the backend allows it deliberately, and the
UI must not add a gate the domain doesn't have.

## Leavers with debt

`/debts` lists students who left owing money, and the dashboard shows the total when there is one.
It is a **list, not a gate** — nothing in the app refuses to re-admit a debtor, and the UI must not
invent a block the domain doesn't have.

Two warnings, at the two moments they matter:

- **Marking someone as returned** — the return already succeeded, so `AttendanceForm` shows the
  amount as an acknowledgement rather than an error, and only then closes.
- **Enrolling a new student** — `findSimilarLeavers` runs as you type the name or phone and warns
  if a past leaver matches. Advisory: real people share names.

The write-off dialog says plainly that it isn't a payment. That matters: the alternative shortcut
(recording money that never arrived) would quietly inflate the revenue reports.

## Dashboard and navigation

The dashboard answers two questions: **who do I chase**, and **what is quietly wrong**.

It used to rank students by **drift** (cumulative days late). Drift is the metric this product is
built on and still sits on every row, but it is the wrong key to sort a worklist by — on the seed
data the largest debtor has one day of drift and used to rank last, while a student with 25 days
of drift may be fully paid up. Money leads; drift breaks ties.

"Needs attention" surfaces problems that raise no error and produce no bill:

- a student on **no pack**, therefore charged nothing month after month;
- a student **marked as gone with no departure date**, whose billing is still running (the state
  migration 0006 deliberately leaves behind rather than inventing a date).

Both render only when non-empty, so a healthy database shows a clean page instead of a row of
green ticks.

**Navigation is destinations only.** "Enrol a student" was a nav entry sitting between Packs and
Reports; it is an action, and now lives as the primary button on the students page — where you
already are when you need it. The monthly and annual reports collapsed into one entry with tabs
inside, for the same reason a nav bar shouldn't enumerate a page's sub-views. Eight items, six.

**`Card` takes `tone`, not a colour override.** Tailwind resolves classes of equal specificity by
their order in the generated stylesheet, not the order they appear in the attribute, so passing
`bg-amber-50` alongside the component's own `bg-white` is a coin flip.

## Money & dates

Money is handled as **decimal strings** end to end (never float math on the client); render with
`formatMoney`. Dates are `YYYY-MM-DD`, months `YYYY-MM`.

## Learn more

- `CLAUDE.md` — architecture, conventions, and domain rules for contributors.
- `FRONTEND_HANDOFF.md` — the authoritative backend contract.
- `sprint-planning.md` — how the frontend was built, sprint by sprint.
