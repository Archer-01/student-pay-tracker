# CLAUDE.md — frontend

The Ardoise app: a Vite + React + TypeScript PWA for one teacher, used mostly on a phone between
classes. It talks to the FastAPI backend in `../backend`, whose OpenAPI schema is the contract
(`npm run gen:api`). Repo-wide rules are in `../CLAUDE.md`. What each screen does, screen by
screen, is in `docs/screens.md`: read it before changing a screen, update it after.

## Commands

```bash
npm run dev            # Vite on :5173, proxying /api to :8000 (the developer's own servers)
npm test               # every test, ~5 s; npm run test:watch to iterate
npm run test:coverage  # the same with coverage, ≥ 85 % or it fails (what CI runs)
npx tsc -b             # typecheck
npm run lint           # eslint
npm run gen:api        # regenerate src/api/schema.d.ts after any backend schema change
npm run build          # tsc + vite build → dist/ (also builds the service worker)
```

`gen:api` dumps the schema with `ardoise openapi` in `../backend`, so it needs no running server.
`src/api/schema.d.ts` is generated: never edit it by hand. CI fails when it is stale.
`allowScripts` in package.json gates native install scripts (esbuild): after changing
dependencies, `npm approve-scripts <pkg>` may be needed.

## Architecture

**API layer (`src/api/`)**, the only place that talks to the server:
- `schema.d.ts`: generated types. `types.ts`: friendly re-exports (`StudentOut`, `LedgerOut`…).
- `client.ts`: the single `fetch` wrapper. Sends `Accept-Language`, builds query strings,
  `credentials: "include"`, and turns failures into `ApiError`. Also `downloadFile()` for PDFs.
- `endpoints.ts`: one function per backend route. **Components never call `fetch` or
  `apiRequest` directly.** `endpoints.test.ts` checks each function's method and path against
  `schema.d.ts`, so a new function needs a line there.

**Auth is an HttpOnly session cookie**, so there is no token for JS to store or send; never add
an `Authorization` header. `lib/auth.tsx` probes `GET /auth/me` on mount and has three states
that must stay distinct: `undefined` (still asking: render neither login nor app, or the form
flashes on every reload), `null` (signed out) and a user. A 401 from anywhere drops to the login
screen through one handler registered in `client.ts`; don't handle 401 per call site. Only a 401
that interrupts a signed-in session sets `sessionExpired`, so a mistyped password never claims the
session expired. Signed out, `App.tsx` renders `<Login />` instead of redirecting, so a deep link
keeps its URL. Accounts come from `ardoise users add`; there is no signup screen. Local dev needs
`COOKIE_SECURE=false` on the backend, or the cookie is dropped over http and everything 401s.

**Routing (`src/App.tsx`)**: every page renders inside `Layout`, with four places: Accueil `/`,
Élèves `/students`, Bilan `/reports` (tabs `monthly`, `annual`, `school`, `leavers`) and Réglages
`/settings` (`classes` and `packs` under it). Old paths (`/classes`, `/packs`, `/debts`,
`/settings/prices`) redirect: keep them, installed apps and bookmarks still use them. Pages live in
`src/routes/`.

**Reads go through `useApi(fetcher, deps)`** (`lib/useApi.ts`): a `loading | error | success`
union with `reload()`. Writes call `endpoints.ts` directly, usually via `useMutation`. A refresh
keeps the current data on screen until the new data lands.

**One payment sheet for the whole app** (`PaymentSheetProvider` in `components/PaymentSheet.tsx`,
provided by `Layout`). Open it with `usePaymentSheet().open(studentId?)`; don't build a second
payment form. Screens that show money put `usePaymentSheet().version` in their `useApi` deps, and
corrections announce themselves with `changed(message)`, so every screen refreshes after a payment
taken anywhere.

## i18n

react-i18next, French and English, catalogues in `src/i18n/locales/{fr,en}.json`. **The app opens
in French** unless English was picked in Réglages; the phone's language is deliberately not
consulted. Tests run in English (the setup resets it).

- Every key goes in **both** catalogues; `src/i18n/catalogues.test.ts` fails on a key in only one.
- **French typography**: a no-break space (U+00A0) before `: ; ? !` and inside `« »`. The same
  test fails on a plain space there. Edit the catalogues with a script that writes
  `json.dumps(..., ensure_ascii=False, indent=2)`, not by hand-pasting.
- **Counts get `_one`/`_other` pairs**; never `{n} {t("students")}` ("1 élèves").
- **No `defaultValue` in `t()`**: it hides a missing key from the tests (how an English "Close"
  once shipped in the French UI).
- The backend localizes its own error `detail` and PDFs from the `Accept-Language` /
  `?lang=` that `client.ts` sends. Non-React modules read the locale from the `i18n` singleton.

## Domain rules the UI must respect

- **Money is a decimal string** (`"300.00"`) end to end. `Number()` only to compare; what is sent
  is always one of the original strings (a French `"199,5"` becomes `"199.5"` by a string edit).
  Render with `formatMoney()`: `"240.00"` → `240 DH`, `"199.50"` → `199,50 DH`.
- **`join_date` is immutable**: no edit control (PATCHing it is a 422).
- **Recording a payment** sends `for_month` (`"YYYY-MM"`) **xor** `cycle_number`.
- **Drift** is cumulative days late, an integer ≥ 0, higher is worse.
- `as_of=YYYY-MM-DD` drives historical views; omit it for today (and omit it, don't send today's
  date: the offline copy is found by the exact address).
- **PDFs go through `downloadFile()`**, never a plain `<a href>`: it carries the session and
  turns a failure into an `ApiError` the screen must show (PDFs are never available offline).
- **No hard delete of students**; leaving is an enrolment period ("Marquer comme parti").
- A student's **note is private**: never on a PDF, those are sent to parents.

## Errors

`ApiError` has `.status`, `.detail` and, for domain errors, `.code`. Domain errors (400/404/409)
carry an already-localized string `detail`: show it via `resolveErrorMessage` (`lib/errors.ts`),
which prefers a catalogue entry `errors.<code>` when one exists. Validation errors (422) carry an
array whose `msg` strings stay English: validate forms client-side for the common cases, and use
`fieldErrors()` to put the rest under their field. A 422 about the request as a whole names no
field and falls back to the form's own message.

## Mobile first

Unprefixed styles are the phone layout; `sm:` and up add what a wider screen can afford.

- **Lists of students are `StudentRow`s**: initials, name, one grey line of facts
  (`useMoneyFacts`), and an `OwedPill` (or similar) on the right. The amount goes in the pill.
- **Bottom bar on a phone, side menu from `lg`**, four places either way. Anything rare goes
  under Réglages; rare student actions go behind "⋯". A page leads with what is done every week.
- **Tap targets are at least 44px** (`min-h-11`); base font is 17px.
- **Dialogs are bottom sheets on a phone** and centred panels from `sm` (`Modal`).
- **Arrows, not dropdowns**, for stepping through months and years (`Stepper`).
- Anything with a fixed pixel width needs a `hidden sm:…` escape, or it pushes content off a
  375px screen. Something fixed to the bottom sits above the tab bar, safe-area inset included.

## Installed as an app

`public/site.webmanifest` declares `display: standalone`, so on a home screen there is no browser
chrome:

- **Edges pad by `env(safe-area-inset-*)`** (`viewport-fit=cover` in `index.html` makes them
  real); `Layout`, the tab bar and the login page already do.
- **No back or reload button**: every page needs its own way back ("‹" links), and screens
  refresh themselves after a change.
- The status bar follows the theme (`<meta name="theme-color">`, set by `lib/theme.tsx` and the
  pre-paint script in `index.html`). Android's bottom bar can't: it takes the manifest's
  `theme_color`, fixed at install, so that stays the brand green.
- Icons (`favicon.svg`, `apple-touch-icon.png`, `icon-*.png`, the maskable one) are the same
  drawing as `components/Logo.tsx`: change them together. `src/installable.test.ts` checks the
  manifest.

## Offline (read only)

The app opens without a connection and shows the last data the server gave for any screen, with a
banner saying how old it is. Nothing is queued for later sending yet.

- **Service worker**: `sw/service-worker.js`, built into `dist/sw.js` by a plugin in
  `vite.config.ts`, registered in `main.tsx` for production builds only (`vite dev` and tests have
  none). Data is **network first**; the stored copy is used only when the network fails or takes
  over 4 s. A server answer, even a 401 or 500, always reaches the app unchanged, so old data never
  hides an expired session. Only successful GETs under `/api/v1/` are stored (not PDFs), stamped
  `x-ardoise-saved-at`; a read with nothing stored gets a 503 with code `offline`.
- **The app's side**: `api/client.ts` reports into `lib/connectivity.ts`; `OfflineBanner` shows
  the age and `useReadOnly()` disables every button that would save something. Screens refetch on
  `online` and when the app returns to the front after 30 s.
- **Every screen is copied, not only the ones opened** (`lib/offlineWarmup.ts`, started by
  `useOfflineWarmup` in `Layout`): while online and on screen, at most every 15 minutes, it calls
  the same `endpoints.ts` functions **with the same arguments** as the screens, because a stored
  copy is found by its exact address. A new screen's reads need adding there.
- **Wiped** on sign-in, sign-out and an expired session (`lib/offlineData.ts`), so one account's
  students never show for another.
- **Testing it** needs `npm run build`, serving `dist`, and stopping the server; browser "offline"
  switches (Playwright's included) don't reach the worker's own requests.
- Recording payments offline is the next phase, not built: it needs a queue of unsent writes
  replayed on reconnecting, telling the teacher about one refused later, and never losing one.

## Look and feel

- **Colours are the semantic tokens** (`brand`, `ground`, `surface`, `ink`, `muted`, `line`,
  and `ok`/`warn`/`bad`/`off` with `-soft` backgrounds), CSS variables in `src/index.css` for light
  and `.dark`. Tailwind's own scales (`slate`, `indigo`…) are unused and don't follow the theme.
  Opacity shorthand (`bg-brand/35`) silently fails on the tokens: add a solid token instead.
- **Status is colour plus words**: green "À jour", amber one month owed, red two or more, grey
  "Sans tarif" (no price set) or « Gratuit » (free on purpose, decision 0011). Never colour
  alone.
- **Type**: Atkinson Hyperlegible for text, Bricolage Grotesque (`font-display`) for titles and
  figures. Digits always come from Bricolage through the `Ardoise Digits` face in `index.css`,
  because Atkinson slashes its zero. Both bundled via `@fontsource`; no request to Google.
- **Theme follows the device** unless chosen in Réglages (`lib/theme.tsx`, mirrored by the
  pre-paint script in `index.html`).

## Motion

Slight, and only where it answers "where did this come from?" or "did that work?"; all of it in
`tailwind.config.js` (`animate-*`), none longer than about a quarter of a second, all switched off
under "reduce motion":

- dialogs rise as a sheet on a phone and fade in from `sm` (`Modal`);
- the payment confirmation slides in, draws its check mark and fades out;
- a pill, a month tile or the status card pops or fades once when what it shows changes
  (`useFlashOnChange`), never on first display;
- buttons and rows answer a tap with a slight press;
- a first load shows `Skeleton` shapes; later refreshes keep the current data until the new
  lands.

No page transitions, counting-up numbers, bars that grow on every visit, bouncing or looping. Add
to this list deliberately.

## Dialogs

Reuse `Modal` for any overlay: it makes `aria-modal="true"` true. A question before a save goes
in the page with `ConfirmBox`, never `window.confirm`: a browser pop-up looks foreign in the
installed app (`ClassDetail` still has one, to move). Focus moves to the first field
(not the × button), Tab wraps inside the panel, closing returns focus to the opener, and the page
behind can't scroll.

## Tests

Vitest + Testing Library on jsdom. `src/test/setup.ts` loads the **real i18n singleton** (so a
missing key fails a test rather than rendering its name), resets the locale to English, and clears
jsdom's `localStorage` after each test. Node's own `localStorage` (Node 25+) is switched off for
the workers in `vite.config.ts`: don't stub `localStorage` per file. `src/test/render.tsx` wraps a
component in a router; mock the API with `vi.spyOn(endpoints, "…")`, never by stubbing `fetch` in a
screen test.

Test **logic and behaviour the teacher would notice**: formatting and locale, the client's two
error shapes, the state machines, and components that make decisions (explicit-null in the edit
form, the pack level warning, the attention block, the write-off flow…). Rendering a `<Card>` and
asserting it has a border is not a test.

Two traps the suite found, worth remembering:

- `Error`'s constructor assigns `message` as an own property, which shadows a prototype getter:
  compute it in the constructor, don't override with a getter.
- A `required` input blocks submission before any handler runs, so a custom "required" message is
  only reachable for whitespace-only input; test each path separately.
