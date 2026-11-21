---
name: api-change
description: Add or change an Ardoise API endpoint, request or response field, or domain error, and carry it through to the screen. Use for any change that crosses backend and frontend - a new route, a new field on a schema, a new error code - so the layers, the generated types, the offline copy and the docs all move together.
---

# Changing the API, end to end

The order matters: each step depends on the one before being right. Tests first at every layer.

## 1. Service (backend/app/services)

- The rule lives here, sync, with no FastAPI and no locale. Date math only here.
- Money through `PricingService.price_of`; never recompute a recorded payment (see the
  invariants in `backend/CLAUDE.md`, and skill `drift-invariants` for anything touching drift).
- A refusal is a `DomainError` subclass in `services/exceptions.py`: a stable `code` plus params,
  never a sentence (`super().__init__("pack_in_use", name=pack.name)`).
- Tests in `tests/integration/test_<service>.py`; `app/services` stays at 100 % (`just cov`).

## 2. Schema and route (backend/app/schemas, backend/app/api)

- Pydantic models in `schemas/`, separate from the ORM. Requests that must not grow fields get
  `model_config = ConfigDict(extra="forbid")`; money is `Decimal`, serialized as a string.
- A new route goes on an existing router (it's gated by where it lives); a new router is mounted
  in `main.py` with `dependencies=GATED`, and `tests/integration/test_api_auth.py` checks it is.
- A new error's HTTP status goes in `api/errors.py` (`_STATUS_BY_ERROR`: 404 not found, 409 conflict;
  anything unlisted is 400), and its message in `app/core/i18n.py` as `error.<code>`, French and
  English (skill `add-i18n-keys`).
- If the CLI does the same thing, keep the two in step (`cli.py`; there are parity tests).
- A schema change in the database is a migration first (skill `new-migration`).
- API tests in `tests/integration/test_api_*.py` with the signed-in `client` fixture.

## 3. Types (frontend/src/api)

```bash
cd frontend && npm run gen:api     # regenerates src/api/schema.d.ts from `ardoise openapi`
```

- Never edit `schema.d.ts`; CI fails when it is stale.
- A new schema gets a friendly name in `types.ts` (`export type PackDetail = components["schemas"]["PackDetailOut"]`).
- A new route gets one function in `endpoints.ts`, and a line in `endpoints.test.ts`'s
  `everyEndpoint` (the test fails until it has one, and checks the method and path against the
  schema).

## 4. Screen (frontend/src)

- Reads through `useApi(() => endpoint(...), deps)`; writes call the endpoint, usually via
  `useMutation`. Anything showing money puts `usePaymentSheet().version` in its deps.
- A screen's new read goes into `lib/offlineWarmup.ts` **with the same arguments** the screen
  uses, or that screen is blank offline (the stored copy is found by its exact address). Omit
  `as_of` for "today" rather than sending today's date.
- Writes are disabled offline: `disabled={readOnly}` from `useReadOnly()`.
- Errors: `resolveErrorMessage(err, t)` shows the backend's localized `detail` (or
  `errors.<code>` from the catalogue when the screen needs its own words); `fieldErrors(err)` puts
  422s under their fields.
- New text in both catalogues (skill `add-i18n-keys`). Screen tests mock `endpoints` with
  `vi.spyOn`.

## 5. Docs and checks

- `docs/decisions/` if the change settles or reverses a decision (check the index first).
- `backend/CLAUDE.md` for a new invariant; `frontend/docs/screens.md` for what
  a screen now does; `backend/README.md` for what shipped.
- `just check` at the root; look at the screen on a phone (skill `ardoise-demo`).
