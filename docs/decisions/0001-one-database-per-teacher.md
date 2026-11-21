# 0001. One SQLite file per teacher, not an `owner_id` column

- Status: Accepted
- Decided: when sign-in landed (BACKLOG §5) · Recorded: 2026-11-21

## Context
Two accounts may use Ardoise (the teacher, and perhaps the school's other teacher one day), and
neither may see the other's students.

## Decision
Each account's data lives in its own SQLite file next to a central one holding accounts and
sessions. Only `api/deps.py::get_db` and `cli.py::_session` know about it. Details in
`backend/CLAUDE.md`, "Per-teacher databases".

## Rejected
- **An `owner_id` column on every domain table**: privacy would depend on ~20 queries each
  remembering its `WHERE`; one forgotten filter leaks a student. It would also share one write
  lock, and make "2BAC / A" unique across both teachers.

## Consequences
- No cross-teacher view is a query; it needs its own design.
- Every migration runs on every file (startup does it); tenant isolation is proven only by
  `tests/integration/test_tenant_isolation.py`, since other tests collapse the files into one.
