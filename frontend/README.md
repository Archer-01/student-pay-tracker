# Ardoise — Frontend

The Ardoise app: React, TypeScript, Vite and Tailwind, installable on a phone's home screen (PWA)
and readable offline. It opens in French; English is in Réglages. The rules it follows are in
[`CLAUDE.md`](CLAUDE.md), what each screen does in [`docs/screens.md`](docs/screens.md), and why
things are the way they are in [`../docs/decisions/`](../docs/decisions/).

## Set up and run

Node 26 (see `.nvmrc`) and the backend running on port 8000 (see
[`../backend/README.md`](../backend/README.md)).

```bash
npm install
npm run dev        # http://localhost:5173, proxying /api to the backend on :8000
```

Sign in with an account made by `ardoise users add`. The backend needs `COOKIE_SECURE=false`
locally, or the session cookie is dropped over http.

## Commands

```bash
npm test               # every test (~5 s); npm run test:watch to iterate
npm run test:coverage  # with coverage, ≥ 85 % (what CI runs)
npx tsc -b             # typecheck
npm run lint           # eslint
npm run gen:api        # regenerate src/api/schema.d.ts after a backend schema change
npm run build          # production build into dist/, with the offline service worker
```

`just check` at the repo root runs everything CI runs, for both apps.

## How it fits

- **Same origin.** The API base is relative (`/api/v1`): in development Vite proxies it to the
  backend, in production the backend serves this app itself, so there is no CORS to set up.
- **One door to the API.** Every call goes through `src/api/endpoints.ts`, typed by the
  generated `schema.d.ts`.
- **Offline.** Only production builds have the service worker; `vite dev` doesn't. To try
  offline mode, build, serve `dist`, then stop the backend (the `ardoise-demo` skill does this
  with demo data).
