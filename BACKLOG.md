# Student Pay Tracker — Backlog v2

Structured specification for the next round of features, expanded from notes taken during the
client conversation with the teacher, then revised after a follow-up round of answers.

**Status:** draft for review. Sections marked **⚠ Decision needed** are still open. Nothing here is
frozen — where the client's original phrasing implied a design that would cause trouble, this
document proposes an alternative and says why (see §2).

**Baseline:** sprints 0–8 are shipped (drift core, models, services, `tracker` CLI, open REST API,
reports/CSV/PDF, ops hardening, en/fr i18n) plus the React SPA. This document covers sprints 9–13.

---

## 0. Reading guide

| Term | Meaning |
| --- | --- |
| **Drift** | Cumulative days late, summed over settled billing cycles. The core metric; never regresses. |
| **Anchor** | `student.join_date` — the immutable date the billing schedule is generated from. |
| **Cycle** | One billing month, indexed from 0 at the anchor. |
| **Override** | Append-only agreed change to future due dates (`anchor_override`), never a mutation. |
| **Offering** | A subject set the teacher sells, e.g. *Maths seul*. Four of them today. Not a table — it's a pack's `name`. |
| **Pack** | A named, **level-scoped**, priced set of subjects — the concrete thing a student is enrolled in, e.g. *Maths seul · 2BAC · 120 DH*. One row per (offering × level) = 24 rows. |
| **Assignment** | Which pack a student is on, at what agreed monthly price, from when. Append-only history. |
| **Class** | A level + name grouping of students, e.g. "2BAC — Groupe A". |
| **Enrollment period** | A contiguous span a student was actually attending. Handles leave/return. |

---

## 1. Roadmap

| Sprint | Feature | Touches drift core? | Risk |
| --- | --- | --- | --- |
| 9 | Classes (level + roster + "Add student" flow) | No | Low |
| 10 | Packs & the pricing model (replaces `student.fee`) | No | **High** — migrates live pricing data |
| 11 | Student profile rework (name split, redoublant, derived first payment) | No | Medium |
| 12 | Enrollment periods: leave & return | **Yes** | **High** |
| 13 | Debt on departure — leavers-with-debt list & re-entry warnings | Reads arrears | Low |
| — | Login / two accounts | No | Deferred, see §5 |

Ordering rationale: risk ramps up, and every sprint is independently shippable.

- **9 before 11** — the student form needs somewhere to put the class field.
- **10 before 11** — same, and the pricing migration is cleaner before the name migration touches the
  same table.
- **11 before 12** — leave dates live on the enrollment period, which supersedes `student.status`.
- **12 before 13** — you cannot flag a leaver with debt without a leave event.

---

## 2. Design changes proposed beyond the notes

The client's answers resolved three questions, and each answer simplifies the build. Two further
changes below are proposals, not instructions — flagged so they're easy to reject.

### 2.1 Enrollment types *are* packs — no second concept (resolves the client's point 3)

The notes described "the pack" (Maths + Physics + French + English, 250 DH) and then, separately,
students who take "Maths only", "Physics only", or "Maths + Physics", plus a request for the ability
to add new enrollment types later.

**These are not two concepts.** A pack is already "a named set of subjects with a price". So:

| Teacher's words | Offering (a pack `name`) | Subjects |
| --- | --- | --- |
| "the pack" | *Pack complet* | Maths, Physique, Français, Anglais |
| "Maths only" | *Maths seul* | Maths |
| "Physics only" | *Physique seul* | Physique |
| "Maths and Physics" | *Maths + Physique* | Maths, Physique |
| any future offering | one new name | whatever it contains |

**Prices vary by level** (confirmed with the teacher), so a pack carries a `level` and each
(offering × level) pair is its own row with its own price: **4 offerings × 6 levels = 24 packs**.

Every student is on exactly one pack. **Adding a new enrollment type is creating rows — zero code,
zero migration, zero deploy.** That is precisely the extensibility the client asked for, and it
arrives for free rather than as a `type` enum that needs a code change every time.

**6 levels, confirmed.** The sixth is **Tronc Commun**, which the teacher does teach — so the grid
is the full 4 × 6 = 24.

Consequence: **`student.fee` disappears** as an independently-typed number (§2.2). The set of packs
*is* the price list.

**Naming.** In code and DB the entity is `pack`. In the UI, only the pack's *name* is shown
("Maths seul", "Pack complet"), with "Pack" as the field label — so the teacher never reads the
odd-sounding phrase "the pack: Maths only". If they'd rather the field said *Formule*, that's an
i18n string, not a schema change.

### 2.2 Pricing lives on an append-only assignment, not on the student (proposal)

**The teacher says pack prices are still unstable.** That moves this from "nice design" to
load-bearing: with 24 prices that will churn for months, the only thing standing between a price edit
and a corrupted billing history is where the price is read from.

The obvious implementation is `student.pack_id` plus reading `pack.price`. It breaks in three
ordinary situations:

1. **A student changes pack mid-year** (adds Physics in January). A mutable FK silently rewrites what
   they owed for October–December.
2. **The teacher raises a pack's price.** Does the student who hasn't paid November owe the old price
   or the new one? A single `pack.price` column cannot answer.
3. **One student gets a discount** (a sibling, a hardship case). There's nowhere to put it without
   inventing a discount model.

One table answers all three, and it matches the house pattern already used for
`payment.expected_due_date` / `payment.days_late` — **snapshot the agreed value at the moment of the
decision, then freeze it**:

```
student_pack_assignment
  id              int      PK
  student_id      int      NOT NULL FK -> student.id  ON DELETE CASCADE
  pack_id         int      NOT NULL FK -> pack.id     ON DELETE RESTRICT
  monthly_price   Numeric(10,2) NOT NULL, CHECK monthly_price >= 0   -- snapshot, not a join
  effective_from  date     NOT NULL
  note            str      NULL      -- e.g. "remise fratrie"
  created_at      datetime NOT NULL
  UNIQUE (student_id, effective_from)
```

- **Effective price for a cycle** = the assignment with the greatest `effective_from` ≤ that cycle's
  expected due date. This is a lookup, not date math, so it stays in `app/services`.
- A pack's `price` is only a **default offered at assignment time**. Editing it never changes any
  existing student's price — no `pack_price_history` table needed.
- A discount is an assignment whose `monthly_price` differs from `pack.price`. No discount model.
- A pack change is a new row. History is preserved automatically.
- Raising the price for everyone is an explicit bulk action, not a side effect:
  `POST /packs/{id}/reprice {price, effective_from, apply_to_existing: true}` writes one new
  assignment per current holder. The teacher sees exactly who was affected.

**Reject this if** the teacher genuinely never changes a price mid-year and never discounts — then
`student.pack_id` + `pack.price` is two columns instead of a table. Given that prices are explicitly
described as unstable, that condition already fails: retrofitting price history after a year of real
data is the expensive version.

### 2.3 The blacklist is advisory, not a gate (resolves the client's point 2)

The client's answer: *"the teacher will check the app manually, ask the student to either pay what
they owe first and enter, or just leave altogether."*

So the app's job is **not** to block re-entry. It is to make it **impossible for the teacher not to
notice**. That removes the whole enforcement mechanism from the original spec — no 409 on return, no
mandatory clearance workflow before re-enrolling. See §3.5 for what's left, which is much smaller.

This also kills the awkward dependency on login: a *blocking* gate needs an audit trail of who
unblocked whom, which needs users. An *advisory warning* needs nobody.

### 2.4 Arrears should be reported in money, not just months (proposal)

`months_overdue` is currently a count. The teacher's actual question at the door is *"how much do
you owe me?"* Once §2.2 lands, `amount_owed` is a straightforward sum of effective prices over unpaid
due cycles. Surface it on the student detail, the class roster, and the leavers list. Small change,
disproportionately useful — and §3.5 needs it anyway.

### 2.5 Per-class exports (proposal)

The monthly report already renders CSV/PDF via `render_table_pdf`. A per-class arrears sheet is
mostly wiring and is the artifact a teacher actually carries into a classroom. Cheap; do it in
sprint 9 while the class endpoints are fresh.

---

## 3. Feature specifications

### 3.1 Sprint 9 — Classes

**User story:** the teacher groups students by school level, opens a class page, and adds students
straight into it without re-picking the class each time.

**Data model**

```
school_class                    -- "class" is reserved in Python; don't name the model that
  id          int      PK
  level       enum     NOT NULL
  name        str      NOT NULL   -- e.g. "Groupe A", "Samedi 14h"
  created_at  datetime NOT NULL
  UNIQUE (level, name)

student
  class_id    int NULL FK -> school_class.id  ON DELETE SET NULL
```

**Levels.** The notes list five. Follow the existing `StudentStatus` pattern (`values_callable`, so
the stored form matches the `?level=` filter value and reads cleanly in exports):

```python
class ClassLevel(StrEnum):
    AC1 = "1AC"; AC2 = "2AC"; AC3 = "3AC"
    TC = "TC"           # ⚠ Tronc Commun — assumed present (see §2.1); drop if not taught
    BAC1 = "1BAC"; BAC2 = "2BAC"
```

Declare them in school order so sorting is natural. Adding a level later is an enum value plus a
migration — acceptable, since the Moroccan level list is stable.

**This enum is shared with `pack.level` (§3.2)** — one definition, imported by both. It is therefore
the single highest-leverage thing to get right in sprint 9: changing it later means migrating two
tables, and the number of pack rows is a multiple of its size.

**⚠ Decision needed (§6 Q2) — can a student be in more than one class?** The notes imply one. One
class per student (nullable FK) is far simpler and is the recommendation. If a student takes Maths
with one group and Physics with another, this becomes a join table and the roster UI changes shape.

**Rules**

- A class with students cannot be deleted → `409`; the UI offers "unassign the students first".
- Students may be unassigned (`class_id = null`); the students list needs an "Unassigned" filter.
- Changing a student's class is a plain `PATCH` and has **no effect on drift, anchor, or payments**.
- A class's level is grouping and display only — the *class* never sets a price. Pricing is the
  pack's job, and packs carry their own `level` (§3.2). The class level's one functional role is to
  **default and sanity-check** which packs are offered when assigning a student (§3.2 rules).

**Endpoints**

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/classes` | `?level=` filter; each item carries `student_count` |
| `POST` | `/api/v1/classes` | `{level, name}` |
| `GET` | `/api/v1/classes/{id}` | Detail + roster with per-student drift and arrears |
| `PATCH` | `/api/v1/classes/{id}` | `{level?, name?}` |
| `DELETE` | `/api/v1/classes/{id}` | `409` if non-empty |
| `GET` | `/api/v1/classes/{id}/roster.csv` · `.pdf` | Per-class arrears sheet (§2.5) |
| `GET` | `/api/v1/students?class_id=` | New filter on the existing endpoint |

**Frontend**

- `routes/ClassesList.tsx` — grouped by level; each card shows student count and total drift.
- `routes/ClassDetail.tsx` — roster reusing the existing `Table` + `DriftBadge` + `OverdueBadge`,
  with an **"Add student"** button routing to `/students/new?class_id={id}`.
- `EnrollStudent.tsx` reads the query param and pre-fills the class field, showing a visible
  *"Adding to 2BAC — Groupe A"* affordance with a way to change it. **Pre-filling invisibly is the
  bug to avoid** — the teacher must be able to see, and correct, which class they're adding to.

**CLI:** `tracker classes add|list|show|rename|delete`.

**Acceptance criteria**

- [ ] `POST /classes` with a duplicate (level, name) → 409 with a stable `code`.
- [ ] "Add student" from a class page lands on a pre-filled form and creates the student in that class.
- [ ] Deleting a non-empty class → 409.
- [ ] Moving a student between classes leaves `cumulative_drift` unchanged (regression test).
- [ ] Class roster PDF renders in both `en` and `fr`.

---

### 3.2 Sprint 10 — Packs & the pricing model

**User story:** the teacher defines the offerings they sell (full pack, Maths only, Maths + Physics,
…) with a price each, assigns one to every student, and can discount or change a student's pack
without corrupting past months.

**Data model**

```
pack
  id          int      PK
  name        str      NOT NULL          -- the offering, e.g. "Maths seul"
  level       enum     NOT NULL          -- ClassLevel, shared with school_class (§3.1)
  price       Numeric(10,2) NOT NULL, CHECK price >= 0   -- default offered at assignment time
  is_active   bool     NOT NULL, default true
  created_at  datetime NOT NULL
  UNIQUE (name, level)                   -- one price per offering per level

subject
  id          int      PK
  name        str      NOT NULL, UNIQUE

pack_subject
  pack_id     int  FK -> pack.id     ON DELETE CASCADE
  subject_id  int  FK -> subject.id  ON DELETE RESTRICT
  PRIMARY KEY (pack_id, subject_id)

student_pack_assignment      -- see §2.2
  ...as specified above
```

A separate `subject` table (rather than free text on the pack) means "Maths" is spelled one way
everywhere and makes "which packs include Physics?" answerable. Subjects are created implicitly by
name when a pack is saved — the teacher must never have to curate a subject list as a separate chore.

**Why `level` sits on `pack` and not in a separate price table.** The teacher's instruction was
explicit: *a pack has a name, a price, and a level*. The normalized alternative — an `offering` table
(name + subjects) plus a `pack_price(offering_id, level, price)` table — would be 4 + 24 rows instead
of 24, and would make the subject list impossible to get out of sync between a level's variants. It's
maybe fifteen extra lines. We're following the teacher's shape because it's their vocabulary and it's
simpler to reason about, and accepting one consequence: **the subject set is duplicated across an
offering's six level-variants**, so a typo can make 2AC's *Maths + Physique* contain only Maths. The
grid UI below is what prevents that, by creating and editing all six variants together rather than as
six independent forms. If that ever stops holding, promoting `name` to an `offering` table is a
mechanical migration — the API shape barely moves.

**Rules**

- A pack has **at least one subject**; `(name, level)` unique; `name` non-blank; `price ≥ 0` (a free
  pack is legal, matching today's `fee = 0` behaviour).
- **All level-variants of an offering carry the same subject set.** Enforced in the service on write
  (creating or editing *Maths seul* writes all six rows' subjects together), and covered by a test
  that asserts the subject sets of same-named packs are identical. This is the cost of denormalizing
  `level` onto `pack`; don't leave it to discipline.
- **A student's pack level should match their class level.** Assignment defaults to the packs matching
  the student's class level, but **warns rather than blocks** on a mismatch — a student may have no
  class yet, or genuinely sit in a group above their level. Never hard-enforce it.
- **Exactly one assignment is active per student at any date.** Overlaps are impossible by
  construction (`UNIQUE(student_id, effective_from)` + service validation that dates are ordered).
- The **first** assignment's `effective_from` must be ≤ `student.join_date`, so cycle 0 always has a
  price. Enforce in the service, test explicitly.
- **Editing a pack's `price` never changes any existing student's price**, and never rewrites
  `payment.amount` on recorded rows. Repricing existing students is the explicit `reprice` action.
- **Packs are never hard-deleted while referenced.** Deactivate (`is_active = false`): hidden from
  the assignment dropdown, still rendered on historical records.
- Removing a subject from a pack does not affect recorded payments or past assignments.
- Arrears logic keeps its current shape: a cycle with effective price `0` owes nothing (this is how
  `fee == 0` behaves today, and that behaviour must not change).

**Migration — the risky part.** `student.fee` currently drives arrears, so the migration must
preserve every existing number exactly.

Today's dev DB has **6 students with 5 distinct fees** (200/250/300×2/350/400). At that size there
is one right answer: **hand-write the mapping.** Ask the teacher, for each existing student, which
class and which offering they're on; put an explicit `student_id → (pack, price)` table in the
migration. Six rows, correct on day one, auditable forever.

The migration therefore **depends on sprint 9 having landed and classes being assigned**, since a
pack is only meaningful with a level. Sequence it that way; don't let sprint 10 start against
class-less students.

Note the students' existing `fee` values (200–400) need not equal the new pack prices — the migration
sets `monthly_price` from the **existing fee**, not from `pack.price`, so nobody's bill changes on
migration day. Divergence between a student's grandfathered price and the current pack price is
exactly what §2.2's snapshot is for, and with unstable prices it will be the normal state, not an
anomaly. Surface it in the UI ("pays 300 DH · pack price 350 DH") rather than hiding it.

If the real DB turns out to hold far more students than the dev copy, fall back to one placeholder
pack per (level, distinct fee), `is_active = false`, plus a "N students still on a placeholder pack"
nudge so it can't quietly become permanent.

Then drop `student.fee`. **Verify the downgrade restores `fee` from the earliest assignment** (see
the updated `new-migration` skill), and test the upgrade against a *copy of the real DB with data*,
not just a blank one — a blank-DB test cannot catch a backfill bug.

**Endpoints**

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/packs` | `?level=` and `?active=` filters; includes subjects and student count |
| `GET` | `/api/v1/packs/grid` | The offerings × levels price matrix — what the UI actually renders |
| `POST` | `/api/v1/packs` | `{name, subjects: string[], prices: {level: price}}` → creates **all** level-variants of an offering in one call |
| `GET` | `/api/v1/packs/{id}` | Detail + current holders |
| `PATCH` | `/api/v1/packs/{id}` | `{price?, is_active?}` — one cell of the grid. Does **not** touch assignments |
| `PATCH` | `/api/v1/packs/by-name/{name}` | `{name?, subjects?}` — offering-wide edits, applied to every level-variant together |
| `DELETE` | `/api/v1/packs/{id}` | `409` if referenced by any assignment — deactivate instead |
| `POST` | `/api/v1/packs/{id}/reprice` | `{price, effective_from, apply_to_existing}` → returns the students affected |
| `GET` | `/api/v1/students/{id}/assignments` | Pack history |
| `POST` | `/api/v1/students/{id}/assignments` | `{pack_id, monthly_price?, effective_from, note?}` — price defaults to the pack's |

**Frontend — the price grid is the feature.** 24 packs whose prices are *unstable* must not be 24
separate forms; the teacher would be clicking through pages to make one round of price changes, and
subject sets would drift apart. Render a **matrix: one row per offering, one column per level, one
editable price per cell**:

```
                    1AC     2AC     3AC      TC    1BAC    2BAC
Maths seul          100     100     120     120     140     150
Physique seul       100     100     120     120     140     150
Maths + Physique    170     170     190     190     220     240
Pack complet        220     220     250     250     280     300
```

- Editing a cell is one `PATCH /packs/{id}`. Editing a row's name or subjects is one
  `PATCH /packs/by-name/{name}` hitting every level-variant, so they cannot diverge.
- Adding an offering adds a row: one form, one `POST`, six packs created.
- Empty cells are legal — an offering not sold at a level simply has no pack there (⚠ §6 Q9: is the
  matrix actually full, or are some combinations not offered?). Don't force 24 rows into existence if
  the teacher only sells 17 of them.
- A cell shows how many students are on it, so a price edit's blast radius is visible before clicking.
- Also: `routes/PackDetail.tsx` (holders, price history) and a pack-history section on
  `StudentDetail.tsx`.

Money is a **decimal string** end to end — render with `formatMoney()`, never do float math on the
client, send strings back. On a grid of 24 editable numbers this is the single most likely bug here.

**CLI:** `tracker packs grid|add|list|edit|deactivate|reprice`, `tracker students assign-pack`.
`tracker packs grid` printing the matrix as a table is the fastest way to sanity-check a price round.

**Acceptance criteria**

- [ ] Migration upgrade **and** downgrade run clean against a copy of the real `app.db`, and every
      student's `months_overdue` is identical before and after (assert on real data, not fixtures).
- [ ] Creating a pack with zero subjects → 422.
- [ ] `POST /packs` with a price per level creates one row per level, all sharing one subject set.
- [ ] Two packs with the same `(name, level)` → 409.
- [ ] Editing an offering's subjects updates every level-variant; a test asserts same-named packs
      always have identical subject sets.
- [ ] Assigning a 2BAC student a 1AC pack succeeds but returns a warning (not a 409).
- [ ] Deleting a referenced pack → 409 with a stable `code`.
- [ ] Editing `pack.price` leaves every existing assignment and every `payment.amount` byte-identical.
- [ ] `reprice` with `apply_to_existing` creates exactly one new assignment per current holder and
      changes nothing for cycles before `effective_from`.
- [ ] A student reassigned mid-year owes the old price for months before the switch and the new price
      after (explicit example test).
- [ ] A student with no assignment covering cycle 0 is rejected at creation, not silently priced at 0.
- [ ] Prices render `250,00` in fr and `250.00` in en.

---

### 3.3 Sprint 11 — Student profile rework

**Target field set** (from the notes, mapped onto the model):

| Field (notes) | Implementation | Status |
| --- | --- | --- |
| ID | `student.id` | exists |
| Name (first and last) | **split** `name` → `first_name` + `last_name` | migration |
| Date of entry | current enrollment period's `entry_date` (§3.4) | sprint 12 |
| Date of leave | current enrollment period's `leave_date` | sprint 12 |
| Phone number | `student.phone` | exists |
| Date of first payment | **derived**, `min(payment.paid_date)` — not stored | derived |
| Redoublant | `student.is_repeating` bool, NOT NULL, default false | new |
| Pack | via `student_pack_assignment` → a level-scoped pack (§3.2) | sprint 10 |
| *(implied)* Class | `student.class_id` (§3.1) | sprint 9 |
| *(existing)* Anchor | `student.join_date` — immutable, shown as "Élève depuis" | keep |
| *(existing)* Fee | removed in sprint 10 | gone |
| *(existing)* Status | derived from enrollment periods in sprint 12 | changes |

**Name split — do not split on the first space.** The existing data already contains
**"Fatima Zahra"**, where *Fatima Zahra* is a compound given name, not first + last. A naive
`split(" ", 1)` would produce `first_name="Fatima", last_name="Zahra"`, which is wrong and will be
wrong for a meaningful share of Moroccan given names (Fatima Zahra, Moulay Ahmed, Sidi Mohammed,
Abdel Illah…).

With only a handful of existing rows, the correct move is a **hand-written mapping in the
migration** — enumerate the real students and split each explicitly. It is a few lines, it is right,
and it is auditable. Reserve the heuristic split for a dataset too large to enumerate, and even then
follow it with a review screen.

The migration must also:

1. Add `first_name` / `last_name`, `NOT NULL` after backfill.
   **⚠ (§6 Q4)** Mononyms: either `last_name = ""` or nullable. Check real data first.
2. Keep a `full_name` **property** on the model (`f"{first_name} {last_name}".strip()`) so the ledger
   PDF subtitle, the download-filename slug (`_slugify_name` / `_ledger_filename` in
   `app/api/students.py`), CSV exports, and the seed all change in exactly one place.
3. Drop `name`, and **verify the downgrade** recomposes it.

Sorting and search work on last name; the API accepts `?q=` matching either part.

**Date of first payment is derived, not stored** — a stored copy is one more thing to keep in sync
with payment correction/deletion, and it's a cheap `min()` over rows the detail endpoint already
loads. Expose it as `first_payment_date: date | None` on `StudentDetailOut`. It is **not** the same
as `join_date`; the gap between them is itself a signal the teacher cares about.

**Endpoints:** `StudentCreate` / `StudentUpdate` / `StudentOut` gain the new fields. `join_date`
stays rejected by `StudentUpdate`'s `extra="forbid"` — **do not relax this** (§4.1).

**Acceptance criteria**

- [ ] Migration upgrade *and* downgrade run clean against a copy of the real `app.db`.
- [ ] "Fatima Zahra" survives the round trip with the correct first/last split (pinned example test).
- [ ] Ledger PDF subtitle and download filename still render/slug the full name.
- [ ] `PATCH /students/{id}` with `join_date` still returns 422.
- [ ] `first_payment_date` is `null` for a student with no payments.
- [ ] Every existing drift/ledger test passes untouched — this sprint must not move a single number.

---

### 3.4 Sprint 12 — Enrollment periods: leave & return

**This is the sprint that touches the drift core.** Property tests are mandatory (see the
`drift-invariants` skill). Do not cut them under time pressure.

**User story:** a student stops attending in March and comes back in October. The teacher records the
leave and the return. The app must not bill them for the months they were away, must not lose the
lateness they had already accumulated, and must not let a return quietly erase their history.

**Data model**

```
enrollment_period
  id            int      PK
  student_id    int      NOT NULL FK -> student.id  ON DELETE CASCADE
  entry_date    date     NOT NULL
  leave_date    date     NULL        -- NULL = currently attending
  leave_reason  str      NULL
  created_at    datetime NOT NULL
  CHECK (leave_date IS NULL OR leave_date >= entry_date)
```

Invariants, enforced in the service and tested explicitly:

- **At most one open period per student** (`leave_date IS NULL`).
- Periods for a student are **non-overlapping** and strictly ordered by `entry_date`.
- The **first** period's `entry_date` equals `student.join_date`. `join_date` stays immutable and
  stays the drift anchor — the schedule is generated from it forever (§4.1).
- Periods are append/close-only; correcting a mistyped date is an explicit amend operation that
  re-validates every invariant, not a general PATCH.

Migration backfills one open period per active student from `join_date`. For students currently
`inactive` we have **no leave date on record** — ⚠ §6 Q5: use `created_at`, the last payment date, or
leave it null and prompt the teacher to fill it in. Prompting is the honest option; inventing a date
here corrupts the very history this feature exists to protect.

**Drift semantics during an absence.** Cycles whose due date falls inside a **closed** gap (after a
`leave_date`, before the next `entry_date`) are **suspended**: excluded from arrears, unable to
accrue drift. The alternatives are both worse — billing a student for months they didn't attend, or
moving the anchor, which erases their real history and rewards the returning debtor (§4.1).

In `LedgerService.get_ledger`:

- Keep generating the full cycle list from the immutable anchor. **`generate_expected_due_dates`
  stays untouched** — it is pure, correct, and 100%-branch-covered. Suspension is a ledger-level
  filter, not a change to the schedule math.
- Add `suspended: bool` to `LedgerEntry`. Suspended cycles render as "away", contribute **0** to
  drift, and don't count toward `months_overdue` or `amount_owed`.
- A cycle that was **already paid is never suspended** — recorded history is frozen truth, exactly
  as with overrides.
- Suspension removes *future* accrual; it never subtracts already-accrued drift.

New hypothesis properties, alongside the existing five:

1. For any set of non-overlapping periods, `cumulative_drift(as_of)` is non-decreasing in `as_of`.
2. Adding a leave/return pair never *increases* drift or arrears at any `as_of`.
3. A student with one open period from `join_date` yields a ledger **identical to today's** — the
   no-absence case is a strict no-op. This is the regression that protects sprints 1–8.
4. Closing and reopening a period on the same day changes nothing.

**`status` becomes derived.** `status: active|inactive` is now "has an open enrollment period".
Keeping both a column and a derived value guarantees they'll disagree. Recommendation: derive it in
the response schema, keep it in `StudentOut` so the existing `?status=active` filter and the frontend
keep working, and remove it from `StudentUpdate` — leaving is the leave endpoint, not a PATCH.

**Endpoints**

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/v1/students/{id}/leave` | `{leave_date, reason?}` → closes the open period. 409 if none open |
| `POST` | `/api/v1/students/{id}/return` | `{entry_date}` → opens a new period. 409 if one is open; 422 if `entry_date` < last `leave_date`. **Never blocked by debt** (§2.3) — returns a warning payload instead |
| `GET` | `/api/v1/students/{id}/periods` | Full attendance history |
| `PATCH` | `/api/v1/students/{id}/periods/{pid}` | Amend a mistyped date; re-validates all invariants |

**Frontend:** an attendance timeline on `StudentDetail.tsx`, "Mark as left" / "Mark as returned"
actions, ledger rows for suspended cycles **visually distinct from unpaid ones** (they are *not*
debt — conflating them is the UI bug to avoid), and a students-list filter for currently-away
students.

**Acceptance criteria**

- [ ] Properties 1–4 above, green.
- [ ] `join_date` is unchanged on the row after a return (assert on the DB, not the response).
- [ ] A student who leaves owing 2 months still owes exactly 2 months after returning.
- [ ] Months inside a closed gap show as suspended and add 0 to drift, arrears, and amount owed.
- [ ] Two open periods cannot exist; a second `POST /return` → 409.
- [ ] The `drift-invariants` skill is updated with the suspension rules as part of this sprint.

---

### 3.5 Sprint 13 — Debt on departure (the "blacklist")

**Revised per the client's answer** (§2.3): this is **advisory, not enforcement**. The teacher checks
the app, then asks the student to pay up or walk. The app's only job is to make that debt impossible
to miss at the two moments it matters.

**User story:** a student who left owing money turns up in September wanting back in. The teacher
needs to see, without going looking for it, that this person owes 500 DH for two months.

**Design: derived, not a stored flag.** A stored boolean goes stale the instant a payment lands.

> A student **left with debt** when they have no open enrollment period **and** their outstanding
> balance as of their last `leave_date` is greater than zero — unless a `debt_writeoff` row exists.

**⚠ (§6 Q6) — what counts as outstanding?** Recommended: unpaid cycles due on or before the last
`leave_date`, each priced at its effective assignment price (§2.2). Suspended cycles are excluded by
construction, since they postdate the leave. Confirm whether the teacher counts the month of leaving:
someone who leaves on the 3rd probably owes it; someone who leaves on the 28th having paid does not.

**Two real outcomes, plus one bookkeeping escape hatch:**

1. **The student pays.** Record the payments → the balance hits zero → the flag clears itself. No
   special workflow, no button. This is the path the client says usually happens.
2. **The student walks.** They stay inactive with the debt on record, permanently. That is correct;
   nothing to build.
3. **The teacher forgives the debt** and readmits them. Without this, the list accumulates ghosts
   forever, and the tempting workaround — recording a fake payment — would falsify the revenue
   figures and the drift history. So:

```
debt_writeoff
  id           int      PK
  student_id   int      NOT NULL FK -> student.id
  reason       str      NOT NULL, CHECK length(trim(reason)) > 0
  amount       Numeric(10,2) NOT NULL      -- snapshot of what was waived
  created_at   datetime NOT NULL
  -- nullable user_id FK added when login lands (§5); a nullable column is a trivial migration
```

Append-only, following the `AnchorOverride` pattern: never a mutation, never a delete. A write-off is
**not** a payment — it must never appear in revenue totals or affect drift.

**Where the warning surfaces** — this is the whole feature:

- On **"Mark as returned"**: a confirm dialog naming the amount and months owed, with *"Record
  payment"* and *"Continue anyway"* as the two exits. `POST /return` succeeds either way and returns
  a `warning` in the payload; the UI decides how loud to be.
- On **new student creation**, when phone number or normalized full name matches a past leaver with
  debt: a warning, **not** a block. Re-enrolling under a fresh record is the obvious loophole, but
  blocking would be wrong — real people share names.
- A **badge** on the student detail and list rows (reuse `OverdueBadge`'s visual language in a
  distinct colour).
- A **dashboard tile**: "N former students owe X DH".
- Recording payments for a flagged student is always allowed — that's the mechanism for clearing it.

**Naming:** call it *leavers with debt* / *impayés* in code and UI, not "blacklist". It describes
what it is, and it doesn't imply an enforcement the app deliberately doesn't do.

**Endpoints**

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/v1/students/leavers-with-debt` | Amount owed, months owed, leave date, phone. CSV + PDF |
| `GET` | `/api/v1/students/{id}/debt` | `{left_with_debt, amount_owed, months_owed, as_of_leave_date, written_off?}` |
| `POST` | `/api/v1/students/{id}/debt/write-off` | `{reason}` → write-off row |
| `GET` | `/api/v1/students?left_with_debt=true` | New filter |

**CLI:** `tracker debts list`, `tracker debts write-off`.

**Acceptance criteria**

- [ ] A student who leaves owing 0 is not flagged.
- [ ] A student who leaves owing 2 months is flagged with the correct **dirham** amount, priced from
      the assignment effective at each unpaid cycle (not the current pack price).
- [ ] Recording the 2 missing payments clears the flag with no further action.
- [ ] `POST /return` on a flagged student **succeeds** and returns the warning payload — it does not 409.
- [ ] A write-off requires a non-blank reason and never appears in revenue totals or drift.
- [ ] Creating a new student with a phone matching a flagged leaver warns but succeeds.

---

## 4. Invariants that must survive all of this

### 4.1 `join_date` stays immutable — including on return

`backend/CLAUDE.md`: *"`join_date` is immutable via the API … the drift model breaks if the anchor
date can move."* Enforced today by `StudentUpdate`'s `extra="forbid"`.

The original notes asked to "update entry date if they come back". Doing that would silently rewrite
the student's entire billing history and reset accumulated drift to zero — which is exactly the
outcome a returning student with unpaid months benefits from, and exactly what the drift model exists
to prevent. §3.4 solves the real need (don't bill for months away) without moving the anchor:
"Date of entry" in the UI is the *current period's* `entry_date`; `join_date` is displayed as
"Élève depuis".

### 4.2 Frozen values stay frozen

Recorded `payment.amount`, `payment.expected_due_date`, and `payment.days_late` are audit truth.
Nothing in this backlog — pack repricing, reassignment, suspension, write-offs — may recompute them.

### 4.3 Layering

No date math in `app/models` or `app/repos`; no DB in `schedule.py`; no FastAPI in services; service
layer stays sync and locale-agnostic (domain exceptions carry a stable `code` + params, never a
formatted sentence). Effective-price lookup is a service concern, not a model property.

### 4.4 `DELETE /students/{id}` vs. the frontend doc

`frontend/CLAUDE.md` claims there is no hard delete and that leaving is `status: "inactive"`. The
backend shipped `DELETE /students/{id}` in `e99a0cd`, and sprint 12 replaces `status` as the
way leaving is recorded. Both statements need rewriting — fix them together in sprint 12.

---

## 5. Deferred: login / two accounts

**Not being built now** — kept in the backlog because it lands at some point.

Sketch, so the reasoning isn't lost: a `user` table (username, display_name, password_hash, role,
is_active), **argon2id** hashing, accounts provisioned via `tracker users add` (no self-service
signup, no email, no password-reset flow), and an **HttpOnly / Secure / SameSite=Lax session cookie**
backed by a server-side `session` table rather than a JWT — because the SPA is same-origin in
production, because server-side sessions can be revoked instantly, and, decisively, because
`frontend/CLAUDE.md` relies on plain `<a href>` links for CSV/PDF downloads: a bearer token in
`localStorage` would break every download link. `/health` stays open for the Docker healthcheck, and
the `tracker` CLI keeps working without a session — it talks to the DB directly and is the
break-glass tool.

**What sprints 9–13 must do now so this stays cheap later:**

- **Don't add `created_by` / `cleared_by` FKs to a `user` table that doesn't exist.** `debt_writeoff`
  deliberately omits one; adding a nullable `user_id` later is a one-line migration.
- **Keep the frontend API seam intact** — every call through `endpoints.ts`, never raw `fetch` in a
  component. Adding `credentials: "include"` and a 401 interceptor then touches one file.
- **Don't build anything user-scoped** (no "my students", no per-user preferences).
- Leave `backend/CLAUDE.md`'s out-of-scope entry as *deferred*, not *forbidden*, so a future session
  doesn't treat it as a settled no.

Open when it lands: do Aymen and Ayoub have identical permissions, or are some actions (deleting
students, repricing packs, writing off debt) owner-only? Recommend shipping identical permissions
with a `role` column already present, so restricting later is route-guard work, not a migration.

---

## 6. Open questions for the client

Each one changes what gets built. Worth a single short call before sprint 9.

1. ~~Tronc Commun — the 24 doesn't match the list.~~ **Answered: TC is a real level.** Six levels
   (1AC, 2AC, 3AC, TC, 1BAC, 2BAC) and 24 packs, as built. (§2.1, §3.1)
2. **One class per student**, or can a student attend more than one group? (§3.1)
3. ~~Does "Maths only" cost the same at every level?~~ **Answered: no.** Prices vary by level, so
   `pack` carries a `level` and there are 24 of them. (§2.1, §3.2)
4. **Existing student names** — are any a single word, and are any compound given names like
   "Fatima Zahra"? Determines the name-split mapping and whether `last_name` can be required. (§3.3)
5. **Existing inactive students** — we have no leave date for them. Fill them in yourself, or leave
   blank? (§3.4)
6. **Month of leaving** — does a student who leaves mid-month owe that month? (§3.5)
7. **Discounts today** — do any current students pay a different price from others on what will be
   the same pack? Confirms §2.2 is worth its table. (§2.2)
8. **Pack price changes** — while prices are still settling, when you change a pack's price should
   students already enrolled move to the new one, or keep what they agreed until you say otherwise?
   (§2.2 assumes: **keep the old one**, with an explicit "apply to existing students" action when you
   want the other behaviour. With unstable prices this is the safer default — the alternative silently
   rewrites what people already owe you.)
9. **Is the price grid full?** 4 offerings × 6 levels = 24 combinations. Do you actually sell all 24,
   or are some not offered (e.g. no *Pack complet* for 1AC)? Empty cells are supported; we just
   shouldn't invent packs you'd never use. (§3.2)
10. **Do the 24 prices exist yet?** If they're still being decided, we can ship the grid with the
    known cells filled and the rest blank rather than waiting for the full matrix. (§3.2)

---

## 7. Cross-cutting requirements

Every sprint inherits the existing house rules — they are not optional:

- **TDD.** Failing test first, minimal code, refactor. No production code without a red test.
- **Alembic migration per model change**, autogenerate reviewed by hand, downgrade verified, and —
  new for this backlog — **backfills tested against a copy of the real DB**, since sprints 10, 11,
  and 12 all migrate live data. See the `new-migration` skill.
- **Layering holds** (§4.3).
- **i18n:** every new user-facing string gets **both** `en` and `fr` — backend catalog
  (`app/core/i18n.py`, completeness is test-enforced) and frontend catalogs
  (`src/i18n/locales/{en,fr}.json`). New copy: class levels, pack and subject labels, leave/return
  actions, suspended-cycle wording, debt warnings.
- **CLI parity:** the `tracker` CLI and the API produce identical results for the same operation.
  Every new write operation gets a CLI verb.
- **`npm run gen:api`** after every backend schema change; `src/api/schema.d.ts` is generated, never
  hand-edited; all calls go through `endpoints.ts`.
- **Skills are part of the deliverable.** Sprint 12 updates `drift-invariants` with the suspension
  rules; any sprint that adds a domain invariant records it there rather than in a commit message.
- **Definition of done** (see the `sprint-done` skill): `uv run pytest` green with coverage on
  `app/services` maintained, `ruff check` clean, `mypy app` clean, `npx tsc -b` clean,
  `npm run lint` clean, both catalogs in sync, README updated, git tag `sprint-N`.
- **Seed data** (`app/core/seed.py`) grows with each sprint: one class per level, the full 4 × 6 pack
  grid, a discounted assignment, a student whose grandfathered price differs from the current pack
  price, a student on leave, a returned student, and a leaver with debt. Without these the new UI
  can't be developed against realistic shapes — and the price grid in particular is unreviewable
  against two packs.

---

## 8. Deliberately out of scope

- **Attendance tracking** (per-session presence). Enrollment *periods* are not attendance — resist
  the slide from one to the other.
- Actually sending WhatsApp/SMS messages (the API returns message text only).
- PostgreSQL. SQLite remains correct for one teacher and hundreds of students.
- Async service layer.
- Multi-teacher / multi-tenant data separation. Both users see the same data.
- Grades, exam marks, report cards.
- **Commission / revenue share between Aymen and Ayoub.** Sketched in `draft-backlog.md` but
  deliberately deferred: the percentages there are ambiguous (20% vs. a flat 50 DH vs. 25% for
  collège may be one rule or three), and the client would rather pin it down later than have a
  money calculation guessed at. Nothing commission-related exists in the code.
- Per-subject billing or partial-month proration. A pack is a flat monthly price; if a student
  changes pack mid-month, the change takes effect from the next cycle.
- Self-service signup, email verification, password-reset emails, OAuth/SSO — even when login lands.
