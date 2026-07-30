# Student Pay Tracker — Frontend

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

## Money & dates

Money is handled as **decimal strings** end to end (never float math on the client); render with
`formatMoney`. Dates are `YYYY-MM-DD`, months `YYYY-MM`.

## Learn more

- `CLAUDE.md` — architecture, conventions, and domain rules for contributors.
- `FRONTEND_HANDOFF.md` — the authoritative backend contract.
- `sprint-planning.md` — how the frontend was built, sprint by sprint.
