# Frontend Handoff — Student Pay Tracker

This backend is **complete** (all 8 sprints, 179 tests green). It's a single-teacher tool for tracking
student tuition payments and **"drift"** (how chronically late a student pays). This document is
everything a frontend needs: how to run it, every endpoint with its shapes, the domain
concepts the UI must get right, and the known gotchas.

> **Read this first:** the API is self-describing. With the server running, open
> **`http://127.0.0.1:8000/docs`** (interactive Swagger) and **`/openapi.json`** (machine-readable).
> Generating a typed client from `/openapi.json` (e.g. `openapi-typescript`, `orval`) is the fastest,
> least error-prone path — treat the shapes below as the human summary, and the OpenAPI schema as the
> source of truth.

---

## 1. Running the backend locally

```bash
# from the repo root
unset DATABASE_URL   # IMPORTANT: a stray shell DATABASE_URL (e.g. Postgres) overrides .env
uv sync
just migrate         # create/upgrade the SQLite database
just run             # → http://127.0.0.1:8000  (fastapi dev, auto-reload)
```

Seed some data quickly via the admin CLI (talks to the DB directly, **no token needed**):

```bash
tracker students add --name "Amina" --join-date 2023-03-05 --fee 300
tracker payments record 1 --date 2023-04-10 --amount 300 --for-month 2023-04
tracker students show 1
```

- SQLite file at `./app.db`. `tracker db reset --yes` (needs `ALLOW_DB_RESET=1`) wipes it for a clean demo.
- `Decimal` money, `date` everywhere — SQLite, single writer, low traffic (~20–30 students).

### ⚠️ CORS is NOT configured yet (backend action needed)

The API has **no CORS middleware**, so a browser app on a different origin (e.g. `http://localhost:5173`)
will be **blocked by the browser**. Before the frontend can call the API from a browser, the backend
must add `CORSMiddleware` allowing the frontend origin. This is a ~5-line change in `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # the frontend dev origin(s)
    allow_methods=["*"], allow_headers=["*"],
)
```

Coordinate with the backend to get this in, or you'll spend an hour confused by CORS errors.

---

## 2. Auth

**There is none — the API is open.** No token, no login, no `Authorization` header on any request.
It's a single-teacher tool meant to run on a trusted host/network. Don't build a login screen or token
handling. (If this is ever exposed publicly, auth becomes a backend concern to add first.)

---

## 3. Conventions (apply to all endpoints)

| Thing | Format / rule |
|---|---|
| Base path | `/api/v1` |
| Dates | `"YYYY-MM-DD"` (e.g. `"2023-04-10"`) |
| Months | `"YYYY-MM"` (e.g. `"2023-04"`) |
| Timestamps | ISO 8601 (`created_at`) |
| **Money** | **JSON strings** in responses (e.g. `"300.00"`). In requests you may send a string or a number; prefer strings and avoid float math on the client. |
| `as_of` | Most read endpoints accept `?as_of=YYYY-MM-DD` (defaults to today). Lets the UI show drift/dashboards "as of" any date — great for historical views and for demoing 2023 data. |
| `status` | `"active"` or `"inactive"` (raw value; localize in the UI — see Localization) |
| Drift | integer = cumulative days late; **higher is worse**. Always ≥ 0. |
| Locale | Send `Accept-Language: fr` (or `en`) on every request — or `?lang=fr` to force one. Controls the language of error messages and CSV exports. Default `en`. |

**Error shapes** (check `response.status`):
- Domain errors (`400`, `404`, `409`) → `{ "detail": "human message", "code": "student_not_found" }`
  — `detail` is localized to the request locale; **`code` is a stable machine string** you can map to
  your own UI copy.
- Validation errors (`422`) → FastAPI's shape: `{ "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }`
  (these `msg` strings stay **English** — validate/localize forms client-side).

---

## 3a. Localization (i18n)

The backend is **English + French**. English is the dev default; French is for the teacher.

- **Set the locale per request:** `Accept-Language: fr` (standard) or `?lang=fr` (wins over the header).
  Have the app send the teacher's language on every call.
- **What the backend localizes:** domain error `detail` messages, and **CSV exports** (headers +
  the ledger status column: `Impayé` / `À temps` / `En retard de N jours`, and `Actif`/`Inactif`).
- **What it does NOT localize:** normal JSON payloads are raw data (numbers, dates, enum values like
  `"active"`) — **the frontend owns its own UI i18n** (labels, buttons, and mapping `status`/error
  `code` to localized copy). 422 field messages are English.
- **Two valid strategies for errors:** show the backend's localized `detail` directly, or ignore it and
  localize by `code` in the frontend. Either works; `code` is stable, `detail` is convenience.

---

## 4. Domain concepts the UI must get right

- **Student** — anchored to an immutable `join_date`. That date is the drift anchor and **can never be
  changed** (the API rejects it). Don't build an edit field for it.
- **Cycle** — a monthly billing period, **0-based from the join month**. Cycle 0 = the join month,
  cycle 1 = the next month, etc. Due dates use the join day-of-month, clamped for short months
  (Jan 31 → Feb 28/29 → Mar 31…).
- **Recording a payment names the month it settles.** Real payments are messy (early, late, prepaid,
  months behind), so the teacher says which month a payment is for — either **`for_month: "YYYY-MM"`**
  (recommended for the UI, human-friendly, resolved server-side) or `cycle_number` (the index shown in
  the ledger). Send **exactly one**.
- **Drift** — sum of `max(0, days_late)` over cycles due by `as_of`. Early/prepaid = 0. It only grows.
  This is *the* metric: sort/flag students by it.
- **Ledger** — the full month-by-month view: paid cycles show the recorded values; **unpaid cycles are
  gaps** (`paid_date: null`) and contribute 0 to drift. Great for an "evidence" screen.
- **Override** — an agreed, **audit-logged** change to a student's due date going *forward* (with a
  mandatory reason). It permanently re-anchors future cycles and **never rewrites past history/drift**.
  Show overrides as a log; creating one requires a reason.
- **Outstanding / latecomers** (dashboard & reports) are computed over **active** students only.

---

## 5. API reference

All paths below are under `/api/v1`. No auth — call them directly.

### Students — read

**`GET /students`** — list. Query: `status`, `sort=drift_desc`, `as_of`.
Returns an array of:
```json
{ "id": 1, "name": "Amina", "phone": "+2126…", "join_date": "2023-03-05",
  "fee": "300.00", "status": "active", "created_at": "2026-07-23T12:00:00",
  "cumulative_drift": 15 }
```

**`GET /students/{id}`** — detail + summary. Query: `as_of`. `404` if unknown.
```json
{ "...StudentOut fields...", "cumulative_drift": 15, "next_expected_date": "2023-07-05",
  "payments_count": 3, "total_paid": "900.00", "as_of": "2023-06-30" }
```

**`GET /students/{id}/ledger`** — cycle-by-cycle. Query: `as_of`. `404` if unknown.
```json
{ "student_id": 1, "as_of": "2023-06-30", "cumulative_drift": 15,
  "entries": [
    { "cycle_number": 0, "expected_due_date": "2023-03-05", "paid_date": null,
      "days_late": null, "amount": null, "cumulative_drift": 0 },
    { "cycle_number": 1, "expected_due_date": "2023-04-05", "paid_date": "2023-04-10",
      "days_late": 5, "amount": "300.00", "cumulative_drift": 5 }
  ] }
```

**`GET /students/{id}/drift`** — cheap number. Query: `as_of`. `404` if unknown.
```json
{ "student_id": 1, "as_of": "2023-06-30", "cumulative_drift": 15 }
```

### Students — write

**`POST /students`** → **201** `StudentOut`. Body:
```json
{ "name": "Amina", "join_date": "2023-03-05", "fee": "300",
  "phone": "+2126…" /* optional */, "status": "active" /* optional, default active */ }
```
`422` on: blank name, `fee < 0`. (Free/discount students are allowed — `fee` may be `0`.)

**`PATCH /students/{id}`** → **200** `StudentOut`. Body (all optional): `phone`, `fee` (≥0), `status`.
- Sending **`join_date`** — or any unknown field — → **422** (the anchor is immutable). `404` if unknown.

**`POST /students/{id}/payments`** → **201** `PaymentOut`. Body:
```json
{ "paid_date": "2023-04-10", "amount": "300",
  "for_month": "2023-04" }          // OR "cycle_number": 1  — exactly one
```
`PaymentOut`: `{ id, student_id, cycle_number, paid_date, expected_due_date, days_late, amount, created_at }`.
- **409** duplicate (a payment already exists for that cycle).
- **422** future `paid_date`, `amount ≤ 0`, neither/both selectors, bad `for_month`, or a month before the student started.
- **404** unknown student.

**`POST /students/{id}/overrides`** → **201** `OverrideOut`. Body: `{ "new_due_date": "2023-07-20", "reason": "agreed shift" }`.
`OverrideOut`: `{ id, student_id, new_due_date, reason, created_at }`.
- **400** invalid (date ≤ join date, or earlier than an existing override). **422** blank reason. **404** unknown.

### Dashboard

**`GET /dashboard/summary`** — Query: `as_of`, `limit` (top-N, 1–100, default 5).
```json
{ "as_of": "2023-06-30", "total_collected_this_month": "500.00",
  "total_outstanding": "800.00",
  "top_latecomers": [ { "student_id": 1, "name": "Amina", "cumulative_drift": 15 } ] }
```
- `total_collected_this_month` = payments whose **paid date** is in `as_of`'s month.
- `total_outstanding` = Σ over **active** students of (unpaid cycles due ≤ `as_of`) × fee.
- `top_latecomers` = active students with drift > 0, most first.

### Reports & CSV exports

**`GET /reports/monthly?year=&month=`** — JSON. `month` 1–12 (`422` otherwise).
```json
{ "year": 2023, "month": 6, "as_of": "2023-06-30",
  "total_collected": "500.00", "total_outstanding": "800.00",
  "rows": [ { "student_id": 1, "name": "Amina", "status": "active", "fee": "300.00",
              "collected": "300.00", "cumulative_drift": 15, "outstanding": "300.00" } ] }
```
Totals equal the sum of the (active-student) rows.

**`GET /reports/monthly.csv?year=&month=`** and **`GET /students/{id}/ledger.csv?as_of=`** — streamed CSV
downloads (`text/csv`, UTF-8 **with BOM** so Excel renders accented/Arabic names; `Content-Disposition:
attachment`). The ledger CSV has a human **Status** column: `Unpaid` / `On time` / `N days late`.

Since the API is open, a plain `<a href="…/ledger.csv" download>` link works for downloads (the
`Content-Disposition: attachment` header makes the browser save it). Once CORS is enabled, `fetch`
+ `blob` also works if you prefer to trigger downloads programmatically.

### Ops

**`GET /health`** → `200 { "status": "ok", "database": "ok" }`, or **503** if the DB is down.

---

## 6. Suggested screens (starter map — not prescriptive)

- **Dashboard** — `GET /dashboard/summary`: collected this month, total outstanding, and the top
  latecomers list. Big-picture landing page.
- **Students list** — `GET /students?sort=drift_desc`: table with name, status, fee, drift; a drift
  badge/heatmap makes chronic latecomers pop. Filter by `status`.
- **Student detail** — `GET /students/{id}` (header/summary) + `GET /students/{id}/ledger` (the
  month-by-month table with paid/late/unpaid rows and running drift). Actions: **record payment**
  (month picker → `for_month`, date, amount), **create override** (new date + reason), **edit
  contact/fee/status** (PATCH). A "Download ledger CSV" link/button.
- **Enroll student** — `POST /students`.
- **Monthly report** — `GET /reports/monthly?year=&month=` with a "Download CSV" button.

---

## 7. Gotchas checklist

- [ ] **CORS** must be enabled on the backend for your origin (see §1) — otherwise nothing works in-browser.
- [ ] **No auth** — don't send an `Authorization` header or build a login; the API is open.
- [ ] **Money is strings** (`"300.00"`). Don't sum with JS floats; use a decimal lib or integer cents, and send strings.
- [ ] **Payments need `for_month` XOR `cycle_number`** — prefer `for_month` (a month picker). Sending both/neither is 422.
- [ ] **`join_date` is immutable** — no edit control; PATCHing it is 422.
- [ ] **Send the locale** (`Accept-Language: fr` or `?lang=fr`) so error messages and CSVs come back
      in the teacher's language; still do your own UI i18n.
- [ ] **CSV downloads** — a plain `download` link works (open API + `Content-Disposition`); add
      `?lang=fr` for a French file.
- [ ] **422 vs 400/404/409** have different `detail` shapes (array vs string) — handle both; domain
      errors also carry a stable **`code`**.
- [ ] Use **`?as_of=`** to power historical/"as of" views; default is today.
- [ ] Only **`sort=drift_desc`** is supported on the students list (no other sort keys yet).

---

## 8. Not in the backend (don't expect these APIs)

- **No messaging/WhatsApp** — sending reminders is out of scope; there's no "send message" endpoint.
- **No auth / multi-user / roles** — the API is open; one teacher, trusted network.
- **Only English & French** — the i18n catalog is `en`/`fr`; other locales fall back to English.
- **No attendance** — payments/drift only.
- **No pagination** on list endpoints (fine for ~20–30 students; ask the backend if the roster grows).
- **No student hard-delete via API** — students who leave get `status: "inactive"` (deletion is refused
  when history exists). Model "left the school" as a status change.

---

## 9. Pointers

- Domain rationale and per-sprint detail: **`README.md`** (sprint-by-sprint) and **`sprint-planning.md`**.
- Working rules/invariants if you touch backend code: **`CLAUDE.md`**.
- The exact request/response schemas live in `app/schemas/` and are surfaced in `/openapi.json`.
```
