---
name: new-migration
description: Use when a SQLAlchemy model in app/models changes (new table, column, or constraint) and an Alembic migration is needed. Ensures autogenerate output is reviewed rather than trusted blindly, constraints match the domain rules, and both upgrade and downgrade are verified.
---

# Creating an Alembic migration

1. Make the model change in `app/models` first — migrations follow the model, not the other way around.
2. Generate a draft: `uv run alembic revision --autogenerate -m "<description>"`.
3. **Read the generated migration by hand.** Autogenerate reliably misses or mishandles:
   - CHECK constraints (e.g. `AnchorOverride.reason` must be NOT NULL and non-empty via CHECK)
   - Column-level NOT NULL on existing tables with data
   - Constraint/index renames
4. Confirm the migration encodes the actual domain rules (`backend/CLAUDE.md`, "Domain invariants") — don't just accept whatever autogenerate produced:
   - `Student.join_date` NOT NULL
   - `Payment.days_late` should be set by the service layer on insert, not a DB-computed column (keeps it testable in `app/services`)
   - `AnchorOverride.reason` NOT NULL and non-empty (CHECK constraint)
5. Check the migration matches the models: `uv run alembic check` against a migrated temp DB
   must say "No new upgrade operations detected" (`test_migrations_match_the_models` runs the same
   check in pytest and CI). `student.class_id` / `pack_id` are filtered in `alembic/env.py`
   (`_INLINE_FKS`): SQLite stores their ON DELETE rule inline, where SQLAlchemy can't read it.
   Don't remove the filter or "fix" it with a rebuild of `student`; the rules are real and pinned
   by `test_student_foreign_keys_keep_their_on_delete_rules`.
6. Test both directions against a blank DB:
   - `alembic upgrade head` → assert the resulting schema matches expectations
   - `alembic downgrade base` (or `-1` for an incremental migration) → assert it leaves the DB clean
7. **If the migration backfills or transforms existing data, a blank-DB test proves nothing.** Splitting
   a column, deriving new rows from old ones, or replacing one pricing field with another can produce a perfectly valid schema holding wrong values. For those:
   - Run the upgrade against a **copy of the real `app.db`**, never the live file.
   - Assert on *values*, not just shape: row counts match, and the numbers the product is judged on
     — `cumulative_drift` and `months_overdue` for every student — are **identical before and after**.
     A migration that moves a drift number is a bug, however clean the schema looks.
   - State explicitly whether the downgrade is lossless. If it can't be (data was destroyed going up),
     say so in the migration's docstring rather than writing a downgrade that silently invents values.
   - Prefer an explicit hand-written mapping over a clever heuristic when the row count is small
     enough to enumerate. A regex that splits names on the first space looks fine until it meets a
     compound given name like "Fatima Zahra", a real case in the teacher's data.
8. After the migration lands, grep `app/models` and `app/repos` for date/day arithmetic — it should find nothing. If you find yourself adding a computed property or default that does date math, that logic belongs in `app/services` instead.
9. Add a focused up/down test to `tests/integration/test_migrations.py` (see `test_0010_…`); the
   stairway test there already walks every revision up, down one and up again.
10. A migration usually carries a data-model decision (a new table instead of a column, what is
    stored versus derived, a lossy downgrade): if it isn't obvious from the code, record it in
    `docs/decisions/` (see `docs/decisions/0001` and `0002`).
