# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Frontend for a **single-teacher student tuition tracker**. The backend (FastAPI, complete) tracks student
payments and **"drift"** — cumulative days a student pays late. This is a Vite + React + TypeScript SPA
that talks to that API. `FRONTEND_HANDOFF.md` is the authoritative backend contract; read it before
touching anything API-related.

## Commands

```bash
npm run dev        # Vite dev server → http://localhost:5173
npm run build      # tsc -b (typecheck) then vite build → dist/
npm run lint       # eslint
npm run gen:api    # regenerate src/api/schema.d.ts from the running backend's /openapi.json
npm test           # vitest run (jsdom); npm run test:watch to iterate
```

- **Typecheck without building:** `npx tsc -b`. Tests are Vitest + Testing Library: `npm test`
  (single run) or `npm run test:watch`.
- `gen:api` requires the **backend running locally** at `http://127.0.0.1:8000`. Re-run it whenever the
  backend schema changes — `src/api/schema.d.ts` is generated, do not hand-edit it.
- **`allowScripts` in package.json** gates native postinstall scripts (esbuild). After changing deps you
  may need `npm approve-scripts <pkg>` for the install script to run.

## Architecture

**API layer (`src/api/`)** — the seam between the app and the backend, layered deliberately:
- `schema.d.ts` — generated OpenAPI types (source of truth for shapes). Never edit by hand.
- `types.ts` — re-exports friendly names (`StudentOut`, `LedgerOut`, …) from the generated schema.
- `client.ts` — the single `fetch` wrapper. Attaches `Accept-Language` (current locale), builds query
  strings, and normalizes errors into `ApiError` (see error handling below). Also `downloadCsv()`.
- `endpoints.ts` — one typed function per backend route. **All API calls go through here**; components
  never call `fetch` or `apiRequest` directly.

**Auth — there is none.** The API is open (single-teacher tool on a trusted host); do not send an
`Authorization` header, build a login/token gate, or add auth state. If the backend is ever exposed
publicly, auth becomes a backend concern to add first.

**Routing (`src/App.tsx`)** — React Router. All pages render inside `Layout` (`src/components/Layout.tsx`,
the nav shell). Route pages live in `src/routes/` and are currently **stubs** awaiting implementation:
`Dashboard`, `StudentsList`, `StudentDetail`, `EnrollStudent`, `MonthlyReport`. Each stub has a TODO
comment naming the endpoint(s) it should call.

**Data fetching (`src/lib/useApi.ts`)** — `useApi(fetcher, deps)` runs an async fetch on mount / when deps
change, returns a discriminated union (`loading | error | success`), and exposes `reload()` for
re-fetching after a mutation. Use it for reads; call `endpoints.ts` functions directly for writes.

**i18n (`src/i18n/`)** — react-i18next, **English + French only** (`en` default). `index.ts` configures the
singleton (bundled `locales/en.json` + `fr.json`), resolves the initial locale from `localStorage` →
browser language → `en`, and keeps `<html lang>` + storage in sync on change. Use `useTranslation()` in
components (`t("nav.students")`); the app owns all its UI copy. Two i18n surfaces work together:
- **Frontend UI copy** — all labels, buttons, `status` values, drift text. Add keys to *both* catalogs.
- **Backend locale** — `client.ts` sends `Accept-Language: <current locale>` on every request and appends
  `?lang=` to CSV downloads, so backend error `detail` and CSV exports come back localized. Non-React
  modules (`client.ts`, `money.ts`) read the active locale from the imported `i18n` singleton.

Drift text uses count-based plurals (`drift.late_one` / `drift.late_other`) — let i18next pick the form
per locale rather than hand-formatting. `formatMoney` formats with the active locale (so fr renders
`300,00`), but the value stays a string end to end.

## Domain rules the UI must respect

These come from the backend contract (`FRONTEND_HANDOFF.md`) and are easy to get wrong:

- **Money is decimal strings** (e.g. `"300.00"`), never numbers. Do not do float math on the client;
  render with `formatMoney()` (`src/lib/money.ts`) and send strings back. Sending a stringified float you
  computed in JS is a bug.
- **`join_date` is immutable.** Never build an edit control for it; PATCHing it returns 422.
- **Recording a payment** sends **`for_month` (`"YYYY-MM"`) XOR `cycle_number`** — exactly one. Prefer
  `for_month` (a month picker). Both or neither → 422.
- **Drift** is an integer, cumulative days late, always ≥ 0, higher is worse. It's *the* metric — surface
  it prominently (see `DriftBadge`). Sort students with `sort=drift_desc` (the only supported sort).
- **`as_of=YYYY-MM-DD`** on most read endpoints drives historical / "as of" views; omit for "today".
- **CSV downloads:** the API is open and sets `Content-Disposition: attachment`, so a plain `<a href>`
  download link works. `downloadCsv()` in `client.ts` (fetch → blob → synthetic anchor click) is still
  provided for programmatic downloads / error surfacing.
- **No hard delete** of students — "left the school" is modeled as `status: "inactive"` via PATCH.

## Error handling

`client.ts` throws `ApiError` with `.status`, `.detail`, and (on domain errors) `.code`. The backend uses
**two different `detail` shapes**: domain errors (400/404/409) return a string plus a stable machine
`code` (e.g. `"student_not_found"`), validation errors (422) return an array of `{loc, msg, type}` whose
`msg` strings stay **English** (localize/validate forms client-side). `ApiError.message` flattens both
into a human string. Two valid strategies for domain errors: show the backend's already-localized
`detail` directly (simplest — it respects the `Accept-Language` we send), or map `code` to your own
i18n copy for full control. Prefer `detail` unless a specific error needs custom UI treatment.

## Backend coordination

- **CORS is handled with a dev proxy, not a backend change.** The backend has no CORS middleware, so
  calling it cross-origin from the browser is blocked. Instead of touching the backend, the Vite dev
  server proxies `/api` → `http://127.0.0.1:8000` (`server.proxy` in `vite.config.ts`), and the API base
  URL is **relative** (`/api/v1`) so requests are same-origin. No CORS involved in dev.
- The API base URL is read from `VITE_API_BASE_URL`, defaulting to the relative `/api/v1`. `client.ts`
  builds the full URL against `window.location.origin`, so a relative base works; override with an
  absolute URL only when the backend is directly reachable (and then it must send CORS headers itself).
- If you point the app at the backend directly (absolute base), CORS becomes a backend concern again.

## Dialogs

`Modal` manages focus, and that is not decoration: `aria-modal="true"` is a promise to assistive
technology that the rest of the page is inert, and the attribute alone does nothing to make that
true. Opening moves focus to the first field (not the × button — these dialogs are mostly forms,
and landing on "close" is a poor first stop), Tab and Shift+Tab wrap inside the panel, closing
returns focus to whatever opened it, and the page behind is locked from scrolling. If you build
another overlay, reuse `Modal` rather than reimplementing the parts that are easy to forget.

## Tests

Vitest + Testing Library, jsdom. `src/test/setup.ts` registers the jest-dom matchers, resets the
locale between tests, and loads the **real i18n singleton** — so tests assert on the copy the
teacher actually sees, and a missing translation key fails a test instead of rendering its own
name. `src/test/render.tsx` wraps a component in the providers every screen assumes (router + i18n).

What is worth testing here, and what isn't: the suite covers **logic**, not markup. Formatting and
locale behaviour, the API client's two error shapes, the `useApi` / `useMutation` state machines,
and the handful of components that make real decisions — explicit-null semantics in the edit form,
the pack level-mismatch warning, the dashboard's conditional attention block, the return-with-debt
acknowledgement, the write-off flow. Rendering a `<Card>` and asserting it has a border is not.

Two things the suite found on the way in, both worth keeping in mind:

- `ApiError` defined `message` as a getter, but `Error`'s constructor assigns `message` as an own
  property and an own data property shadows a prototype getter — so every validation error read
  back as the literal "Validation error". Compute in the constructor, don't override with a getter.
- A `required` input means the browser blocks submission before any handler runs, so a custom
  "field is required" message is unreachable for an empty value. Ours exists for whitespace-only
  input, which `required` accepts; the tests assert each path separately.
