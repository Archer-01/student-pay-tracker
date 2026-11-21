---
name: sprint-done
description: Verify a sprint's Definition of Done and (if it passes) tag the sprint. Use when the user asks "is sprint N done", "close out this sprint", "can I tag sprint N", or before creating a `sprint-N` git tag.
---

# Sprint Definition of Done

Per `sprint-planning.md`, every sprint (0–8) is only done when all of the following are true. Check each one in order and stop at the first failure — don't tag a sprint that isn't actually done.

**Sprints 9+ (`../BACKLOG.md`) also span the frontend and the i18n catalogs** — run checks 7–9 below in addition. A backend-green sprint whose SPA doesn't typecheck is not done.

1. **Tests green:** run `uv run pytest`. Must exit clean with no failures.
2. **Coverage:** if `app/services` exists, confirm the coverage threshold (85%, configured in `pytest.ini` per Sprint 0) is met for that package. Sprint 1 in particular requires 100% branch coverage on `services/schedule.py` — check this explicitly for that sprint.
3. **Lint clean:** run `uv run ruff check`. Must report no issues.
4. **Types clean:** run `uv run mypy app`. Must report no errors (strict on `app/services`).
5. **README updated:** confirm the README has a section describing what shipped this sprint and how to run it. If missing, write it before proceeding — don't tag undocumented work.
6. **No leaked business logic** (relevant from Sprint 2 onward): `grep` `app/models` and `app/repos` for date/day arithmetic — should find nothing. Domain logic belongs in `app/services`.

7. **Frontend clean** (sprints 9+, run from `frontend/`): `npm test`, `npx tsc -b` and `npm run lint` all clean. Note `npx tsc -b | head` masks the exit code — check `$?` or run it bare. If the backend schema changed, confirm `npm run gen:api` was re-run and `src/api/schema.d.ts` is current — a stale generated file typechecks fine and lies.
8. **i18n catalogs in sync** (sprints 9+): every new user-facing string exists in **both** `en` and `fr`, backend (`app/core/i18n.py`) and frontend (`src/i18n/locales/{en,fr}.json`). The backend has a completeness test; the frontend does not — diff the two JSON key sets.
9. **Skills updated** (sprints 9+): if the sprint added or changed a domain invariant, it belongs in the relevant skill (e.g. `drift-invariants` for anything touching drift), not just in a commit message. An invariant that only exists in git history will be broken by the next session.

## Reporting

Summarize each check as pass/fail. If everything passes, propose the exact tag command (`git tag sprint-N`) and ask for confirmation before running it — tagging is a durable action, don't do it silently. If anything fails, list what's missing and stop; do not tag.
