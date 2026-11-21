---
name: parallel-agents
description: Split Ardoise work across several subagents running at once without them colliding. Use when a task has independent pieces (tests for separate screens, features in separate files, a review alongside a build) and running them in parallel would save real time. Covers file ownership, worktrees, scratch paths and ports, the brief, and checking what comes back.
---

# Running agents in parallel

Worth it when the pieces are genuinely independent and each takes more than a few minutes. Not
worth it for a handful of edits, or when the pieces change the same code: then one agent, or you,
in sequence.

## Who owns what

Every agent gets an explicit list of the files it may create or edit, and is told to touch
nothing else. Then pick the mode:

- **Same checkout** when each agent only **creates new files** (tests for different screens, a
  new skill each). Simple, and nothing to merge. Tell them not to run git commands that change
  state.
- **Worktrees** (`isolation: "worktree"` on the Agent call) when agents **edit existing files**.
  Each works on its own branch; you merge them one by one into an integration branch, run
  `just check` there, then merge to main.

Files several pieces always want, so give them a single owner or keep them for yourself:

- **The translation catalogues** (`frontend/src/i18n/locales/{fr,en}.json`). Have each agent
  write its new keys to its own JSON file (`{"fr": {...}, "en": {...}}`), and add them afterwards
  with `add-i18n-keys`'s `i18n.py set --file`.
- `frontend/src/api/schema.d.ts` (regenerate once, after merging the backend changes),
  `types.ts`, `endpoints.ts` and `endpoints.test.ts`, `lib/offlineWarmup.ts`.
- `backend/app/core/i18n.py`, `api/errors.py`, `services/exceptions.py`, `main.py`.
- Migrations: one agent at a time, since each takes the previous revision as its parent.
- The CLAUDE.md files and `frontend/docs/screens.md`: update them yourself at the end.

## Scratch space, ports, servers

- Each agent writes only under its own scratch folder: `<scratchpad>/<agent-name>/`. Shared
  names like `shots/` or `seed.py` get overwritten by whoever runs last; this has happened.
- An agent that needs the running app starts its own demo (skill `ardoise-demo`) in its folder
  on its own ports: `API_PORT=8002 WEB_PORT=5176`, `8003/5177`… Never 8000 or 5173.
- Agents don't commit or push; you do, after checking.

## The brief

An agent knows only what the brief says. Include:

1. **The goal** in a sentence, and why.
2. **Files it owns** (create/edit), and "touch nothing else".
3. **What to read first**: the relevant CLAUDE.md sections, `frontend/docs/screens.md`, one or
   two existing files to imitate.
4. **Conventions** it would otherwise get wrong (tests run in English; mock `endpoints` with
   `vi.spyOn`; money as strings; French typography; which skill applies).
5. **Done means**: the exact commands that must pass for its files (`npx vitest run <files>`,
   `npx tsc -b`, `uv run pytest <files>`), and no stderr noise.
6. **Report**: files changed, what was tested, results, and **suspected bugs it found but did not
   fix** (file:line, what, why). Bugs outside its files are yours to judge.

## When they come back

- Don't take the report's word for it: run the full suite (`just check`) with everything merged.
- Check each reported bug yourself before fixing it; they are often right, sometimes not.
- Look for duplicates (two agents adding the same helper) and for drift from the conventions.
- Then commit, in pieces that each make sense.
