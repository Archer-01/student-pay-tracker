# CLAUDE.md — Ardoise

Ardoise tracks tuition payments and lateness ("drift") for one tutoring teacher, who uses it on
an iPhone between classes, in French. It is in production (one Docker image on Northflank's free
tier) with **real student data**. Two apps in one repo:

- `backend/`: FastAPI + SQLite, one database file per teacher. Rules in `backend/CLAUDE.md`.
- `frontend/`: React PWA, installable, readable offline. Rules in `frontend/CLAUDE.md`; what each
  screen does in `frontend/docs/screens.md`.
- `FRONTEND_HANDOFF.md`: the API contract between them (the OpenAPI schema is the truth).

## Commands

```bash
just check                     # everything CI runs, both apps: run it before calling work done
cd backend && just test        # backend tests, ~5 s (just cov for coverage, just lint)
cd frontend && npm test        # frontend tests, ~5 s (npm run test:coverage, npx tsc -b, npm run lint)
cd frontend && npm run gen:api # after any backend schema change; CI fails on a stale schema.d.ts
```

## Hard rules

- **Never stage a database, a backup, or anything in `backend/local-prod/`**: they hold real
  students' names and phone numbers. They are gitignored, and `.claude/hooks/guard-bash.sh`
  refuses to stage them.
- **Ports 8000 and 5173 are the developer's own servers**: never stop or restart them. Run
  scratch servers on other ports (backend 8001, Vite 5174+) and stop them by PID.
- **Commit only when asked; the developer pushes.** One commit per coherent change, with a
  message that says why.
- **Every user-facing string exists in French and English**, with French typography (U+00A0
  before `: ; ? !`). Both apps have tests enforcing it.
- **Money is a decimal string end to end**; drift, recorded payments and `join_date` follow the
  invariants in `backend/CLAUDE.md`.

## Changing things

- **An API change** goes backend schema + tests → `npm run gen:api` → `src/api/types.ts` →
  `endpoints.ts` + `endpoints.test.ts` → the screen. A new screen read also goes into
  `frontend/src/lib/offlineWarmup.ts`, so it works offline.
- **A schema change** is an Alembic migration (skill `new-migration`), checked up, down and
  against the models.
- **Docs move with the code**: the area's CLAUDE.md for rules, `frontend/docs/screens.md` for
  screen behaviour, `backend/README.md` for what shipped.
- **Parallel agents** each own distinct files; when two would edit the same file, use git
  worktrees and merge. Give each its own scratch file names.

## Harness

`.claude/settings.json` wires the hooks (`guard-bash.sh` before Bash, `format-python.sh` after
edits); shared skills live in `.claude/skills/`. CI is `.github/workflows/ci.yml`, one job per
app, and `.pre-commit-config.yaml` is an optional local gate with the same tools.
