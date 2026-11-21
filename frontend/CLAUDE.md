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
- `gen:api` shells out to `ardoise openapi` in `../backend`, so it needs **no running server** —
  `/openapi.json` is behind the session gate now, and a CLI dump sidesteps that entirely. Re-run it
  whenever the backend schema changes; `src/api/schema.d.ts` is generated, do not hand-edit it. The
  intermediate `.openapi.json` is gitignored.
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

**Auth — a session cookie, and nothing for this code to store.** The backend gates every `/api/v1`
route except `/auth/*`. The session lives in an **HttpOnly cookie**, so JS cannot read it and there
is no token to keep in `localStorage`: `client.ts` sets `credentials: "include"` on every request
and the browser does the rest. Never send an `Authorization` header.

- `lib/auth.tsx` (`AuthProvider`) owns "who is signed in" and probes `GET /auth/me` on mount. Three
  states, and the distinction matters: `undefined` = still asking, `null` = signed out, a user =
  signed in. Rendering the login form while `undefined` flashes it on every reload.
- **401 from anywhere** drops the app to the login screen, via `setUnauthorizedHandler` in
  `client.ts`. Registered once centrally — do not handle 401 per call site.
- **`sessionExpired` distinguishes being *cut off* from being signed out.** Only a 401 that
  interrupts an already-signed-in session sets it; a failed login or a cold start must not, or the
  app would claim your session expired when you simply mistyped a password.
- `App.tsx` swaps the whole tree rather than redirecting: signed out, `<Login />` is all that
  renders, so a deep link like `/students/3` keeps its URL and lands there after signing in.
- This gate is **convenience, not security**. Every figure comes from a gated API call, so bypassing
  it yields a shell full of 401s.
- Accounts are created with `ardoise users add` on the backend. There is no signup screen — don't
  build one (see `backend/CLAUDE.md`).
- **Local dev needs `COOKIE_SECURE=false` on the backend.** Over plain http a `Secure` cookie is
  silently dropped, which presents as "login succeeds, then everything 401s".

**Routing (`src/App.tsx`)** — React Router. All pages render inside `Layout` (`src/components/Layout.tsx`),
which has four places: Accueil `/`, Élèves `/students`, Bilan `/reports` (tabs: monthly, annual,
`school`, `leavers`) and Réglages `/settings` (with `classes` and `prices` under it). Old paths (`/classes`,
`/packs`, `/debts`) redirect, so keep those routes. Pages live in `src/routes/`.

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
per locale rather than hand-formatting. Never compose a count with a word (`{n} {t("students")}` reads "1 élèves");
give it a `_one`/`_other` pair. French text follows French typography — a no-break space (U+00A0)
before `: ; ? !` and inside `« »` — and `src/i18n/catalogues.test.ts` fails on a plain space there,
or on a key present in only one catalogue. Don't pass `defaultValue` to `t()`: it hides a missing
key from that test and from the setup's missing-key check, which is how an English "Close" once
shipped in the French UI. `formatMoney` formats with the active locale and names the currency,
dropping cents when there are none (`"240.00"` → `240 DH`, `"199.50"` → `199,50 DH` in French);
the value stays a string end to end. The app opens in French unless someone picked English in
Réglages — the phone's own language is deliberately not consulted.

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
- **PDF downloads go through `downloadFile()`** in `client.ts` (fetch → blob → synthetic anchor
  click), never a plain `<a href>`. Two reasons, and the second is now load-bearing: it surfaces
  errors as an `ApiError` instead of downloading an error page, and a bare anchor would not carry
  the credentials the gated API needs. (`BACKLOG.md` §5 once argued the reverse — that anchors
  forced cookie auth — but the anchors were already gone by the time login landed.)
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

## Mobile first

The teacher uses this on a phone between classes, so the unprefixed styles are the phone layout
and `sm:` upward adds what a wider screen can afford. Concretely:

- **Lists of students are `StudentRow`s** (`src/components/StudentRow.tsx`): initials, name, one
  grey line of facts, and something on the right (usually an `OwedPill`). Accueil, Élèves, a class
  roster and Bilan's per-student list all use it, so a teacher learns to read one row. Put the
  amount in the pill and everything else in the grey line (`useMoneyFacts` gives the usual months
  unpaid and lateness), or names get cut off on a phone.
- **Navigation is a bottom bar on a phone and a side menu from `lg` up**, four items either way.
  The old top bar was 602px wide on a 390px screen and hid two of its six items. Anything rare
  (classes, prices, language, appearance, sign-out) goes under Réglages, not into the bar.
- **Pages pad their bottom** for the tab bar; `Layout`'s `<main>` already does. Something fixed to
  the bottom of the screen (a toast, a floating button) sits above it, safe-area inset included.
- **Dialogs are bottom sheets on a phone** and centred panels from `sm` up (`Modal`).
- **Rare actions go one level down**: a student's edit, departure, payment-day change and PDF sit
  behind "⋯"; classes and prices under Réglages. A page leads with what is done every week.
- **Arrows, not dropdowns**, for stepping through months and years (`Stepper` in
  `src/components/report.tsx`, with `Figure` and a plain-element `BarChart`).
- **A pack is one name at one level**, listed and edited on its own (Réglages › Packs,
  `routes/PacksList.tsx`). There is no grouping of packs across levels any more: the teacher names
  each pack for its level ("Pack TC Scientifique"), and an offer × level grid was mostly empty
  cells. A pack's level is locked once a student has it (the server refuses it too). The backend's
  offering and grid endpoints still exist for the CLI; the app doesn't call them.

Anything with a fixed pixel width needs a `hidden sm:…` escape or it will push real content off a
375px screen.

## Installed as an app

`public/site.webmanifest` declares `display: standalone`: added to a phone's home screen, Ardoise
opens with no address bar or tabs. That changes a few things to keep in mind:

- **The page runs to the top of the screen.** Anything at an edge pads by
  `env(safe-area-inset-*)`, as `Layout`'s `<main>` and side menu (top), the tab bar (bottom) and
  the login page already do; `viewport-fit=cover` in `index.html` is what makes those insets real.
- **The status bar is the page's top edge**, so its colour (`<meta name="theme-color">`) follows
  the theme actually showing: `lib/theme.tsx` sets it, and the pre-paint script in `index.html`
  sets it before React loads.
- **The bottom (navigation) bar on Android can't follow the theme.** Chrome and Brave colour it
  from the manifest's `theme_color`, fixed at install, and the meta tag only reaches the top bar.
  It is the brand green, which reads under either theme's tab bar; the light ground it used to
  be left a light strip under the dark theme. An installed app picks up a manifest change when
  the browser next checks it (up to a day), or at once when reinstalled.
- **There is no browser back or reload button.** Every page needs its own way back (the "‹"
  links), and screens refresh themselves after a change rather than relying on a reload.
- **Offline, read only** (see "Offline" below): the installed app opens without a connection and
  shows the last data it saw.
- **Icons:** `favicon.svg`, `apple-touch-icon.png` (180px, square: iOS rounds it), `icon-192.png`,
  `icon-512.png`, and `icon-maskable-512.png`, whose slate sits inside the central safe circle
  with the wood running to the edges, so any launcher shape crops cleanly. Same drawing as
  `components/Logo.tsx`; change them together. `src/installable.test.ts` checks the manifest.

## Offline

Read only, by design: the app opens without a connection and shows the last data each screen
saw, with a banner saying so and how old it is. Nothing is stored for later sending.

- **The service worker** is `sw/service-worker.js`, built into `dist/sw.js` by the
  `ardoise-service-worker` plugin in `vite.config.ts` (which writes in the build id and the files
  to keep), and registered in `main.tsx` for production builds only. `vite dev` and the tests run
  without one.
- **Data: network first, stored copy only when the network fails** or takes over 4 seconds. A
  server answer, even a 401 or a 500, always reaches the app unchanged: old data must never hide
  an expired session. Only successful GETs under `/api/v1/` are stored (not PDFs), stamped with
  `x-ardoise-saved-at`; a read with nothing stored gets a 503 with code `offline`.
- **The app reads those two signals** in `api/client.ts` and reports into `lib/connectivity.ts`:
  `OfflineBanner` shows the time, and `useReadOnly()` switches off the buttons that would save
  something (payments, adding or editing students, classes, packs). A write that still finds no
  network fails with code `network` and a sentence saying nothing was saved. Screens refetch on
  the browser's `online` event, which turns them live again.
- **The stored data is wiped** on sign-in, sign-out and an expired session (`lib/offlineData.ts`,
  from `lib/auth.tsx`), so one account's students never show for another.
- **Updates:** every build has a new id, so a deploy ships a new worker; it takes over at once and
  deletes the previous build's files. Pages themselves are fetched network-first.
- **Testing it** needs a production build: `npm run build`, serve `dist`, and cut the connection
  by stopping the server. Browser "offline" switches (Playwright's included) don't reach the
  service worker's own requests.
- **Recording payments offline (level 3) is not built.** It would add a queue of unsent writes,
  replayed on reconnecting. The backend already refuses a second payment for the same month,
  which is what would make replaying safe; the open questions are telling the teacher about a
  payment refused later, and never losing an unsent one.

## Look and feel

The design tokens live in `src/index.css` (CSS variables, light and `.dark`) and are exposed to
Tailwind in `tailwind.config.js` as semantic names: `brand`, `ground`, `surface`, `ink`, `muted`,
`line`, and the status pairs `ok`/`warn`/`bad`/`off` (each with a `-soft` background). **New code uses
those names.** `indigo` and `slate` are remapped to the brand and its neutrals only so that screens
not yet rebuilt match; don't reach for them in new code.

- **Status is colour plus words**: green "À jour", amber for one month owed, red for two or more,
  grey "Sans tarif". Never colour alone.
- **Type**: Atkinson Hyperlegible for text (built for legibility), Bricolage Grotesque
  (`font-display`) for titles and big figures. Digits always come from Bricolage, through the
  `Ardoise Digits` face in `index.css`, because Atkinson slashes its zero and "2Ø26" reads as a
  serial number. Both are bundled via `@fontsource`; the app makes no request to Google.
- **Base size is 17px** (`html { font-size: 106.25% }`), and tap targets are at least 44px
  (`min-h-11`).
- **Theme follows the device** unless someone chose light or dark in Réglages
  (`lib/theme.tsx`; the pre-paint script in `index.html` mirrors the rule).

## Motion

Slight, and only where it answers "where did this come from?" or "did that work?". The full set
is defined in `tailwind.config.js` (`animate-*`), nothing runs longer than about a quarter of a
second, and `index.css` switches all of it off under the device's "reduce motion" setting:

- dialogs rise as a sheet on a phone and fade in from `sm` up (`Modal`);
- the payment confirmation slides in, its check mark draws itself, and it fades out;
- a pill, a month tile or the student's status card gives one small pop or fade when what it
  shows changes (`useFlashOnChange`): never on first display, so opening a screen animates nothing;
- buttons and rows answer a tap with a slight press;
- a screen's first load shows grey placeholder shapes (`Skeleton`), and later refreshes keep the
  current data on screen until the new data lands (`useApi`), which is also what lets a row
  change in place after a payment instead of blinking out and back.

No page transitions, no counting-up numbers, no bars that grow on every visit, nothing that
bounces or loops. Add to this list deliberately, not by habit.

## Taking a payment

There is one payment sheet for the whole app, provided by `Layout` (`PaymentSheetProvider` in
`src/components/PaymentSheet.tsx`). Open it with `usePaymentSheet().open(studentId?)`; without an id it
starts on a student picker that lists the students who owe first. Don't build a second payment
form. Screens that show money put `usePaymentSheet().version` in their `useApi` deps, so they
refresh themselves after a payment taken from anywhere.

The sheet opens filled in (`src/lib/paymentDefaults.ts`, with its own tests):

- **Month**: the oldest unpaid month that is actually owed (months the student was away for are
  skipped), with the next month offered last for paying in advance.
- **Amount**: what the student paid last time, unless that is above their current price, in
  which case the price. Not the price by default: several students pay less than their listed
  price, and starting there invites the over-payment typo the backend cap exists for.
- **Date**: today.

Money stays a string throughout: `Number()` only compares, and the value sent is always one of
the original strings (a French "199,5" is turned into "199.5" by a string edit).

## Accueil

Top to bottom: the month as a title; two figures, what came in this month (all cash, back
payments included, with the teacher's part under it) and what is owed today; **Mensualités du
mois**, this month's fees against what has been paid toward them, as a count of students and a
bar (hidden in a month where nobody is due); the pay button; anything needing attention; **À
relancer**; **Cette semaine**, the unpaid dues of the next seven days, soonest first, said as
"aujourd'hui", "demain" or the day (hidden when empty); and the link to former students who left
owing. The server computes both new lists (`this_month`, `due_this_week` on the dashboard
summary), from the same override-aware schedule as the student page.

## Bilan › École

The school's share of each month, and whether it was handed over (`routes/SchoolShare.tsx`). It
leads with the latest month still to hand over and **Marquer comme remis** (today, or another
day); below, every month in words: "Remis le 3 nov.", "Il manque 50 DH" (a payment recorded
after the month was settled), "À remettre", "Rien à remettre". A handed-over month can have its
date changed or the handover undone (asked first). While last month's share is outstanding, the
Accueil's "À vérifier" box says so and links here.

## The student page

The school year is twelve tiles, September to August (`src/lib/schoolYear.ts`, with its own tests):
paid, paid late, owed, away (not owed), not yet due, or nothing expected (before joining, after
leaving). The ledger already holds every month that has come due plus any paid in advance, so a
month without an entry is either upcoming or not expected; whether the student is still enrolled
decides which. Tapping an owed tile opens the payment sheet on that month.

Tapping a paid tile shows what was recorded and, online, lets a typo be fixed:
**Modifier ce paiement** (`EditPaymentForm`: amount and date, sending only what changed) or
**Supprimer ce paiement**, which asks first in the same sheet and says the month will be owed
again. There is no "move to another month": that is delete, then record the right month, and the
confirmation says so. Both announce themselves through `usePaymentSheet().changed(message)`,
which bumps the same `version` as a recorded payment, so every screen refreshes and the same
toast appears.

**Ponctualité** (in Détails, and as a chip on the students list, latest payers first): the
server's `average_days_late` over the student's last six payments, read as À l'heure (0–2 days),
Un peu tard (3–7) or Souvent tard (8+) by `lib/punctuality.ts`. Hidden until a first payment is
due. It reads the frozen lateness of payments; it is not drift and changes nothing.

Under the status card sits the teacher's **note** on the student (`student.note`, up to 500
characters, edited in `EditStudentForm`), or a quiet "Ajouter une note" link when there is none.
It is private: it never goes on a PDF, since those are sent to parents.

The departure/return action follows the **enrolment periods**, not `status`: a student set to
inactive by hand still has an open period, and only "Marquer comme parti" fixes that. The edit form
has no status field for the same reason.

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
