# Decisions

Short records of choices that someone, or an agent, could otherwise "fix" by mistake: why it is
this way, what was rejected, and when to think again. The rules themselves live in the
CLAUDE.md files; these hold the reasons.

**Before changing anything a record covers, read it.** To change a decision, don't edit the old
record: write a new one, mark the old one `Replaced by NNNN`, and update the index.

**Write one** when a choice is non-obvious from the code, or was settled in a conversation (with
the developer or with the teacher), or rejects an option that will look tempting later. Not for
every change: a commit message is enough for those.

## Index

| # | Decision | Status |
|---|---|---|
| [0001](0001-one-database-per-teacher.md) | One SQLite file per teacher, not an `owner_id` column | Accepted |
| [0002](0002-current-pricing.md) | Prices are current, not historical | Accepted |
| [0003](0003-web-app-not-native.md) | A web app (PWA), not a native app, for now | Accepted |
| [0004](0004-northflank-single-copy.md) | Northflank holds the only copy of the data; backups come later | Accepted |
| [0005](0005-session-cookie-no-csrf.md) | A session cookie, and no CSRF token | Accepted |
| [0006](0006-offline-read-only-first.md) | Offline is read-only first; recording payments offline comes next | Accepted |
| [0007](0007-zero-payments.md) | A 0 DH payment is allowed on purpose | Replaced by 0011 |
| [0008](0008-cli-rework-pending.md) | The CLI will be reworked; its known bugs wait for it | Replaced by 0010 |
| [0009](0009-leavers-debt-is-a-warning.md) | A leaver's debt is a warning, never a block | Accepted |
| [0010](0010-cli-is-an-admin-tool.md) | The CLI is an admin tool, not a second app | Accepted |
| [0011](0011-free-students.md) | A student can be free on purpose | Accepted |

## Template

```markdown
# NNNN. <The decision, as a sentence>

- Status: Accepted | Accepted, not built | Replaced by NNNN
- Decided: <date or period> · Recorded: <date>

## Context
What made a choice necessary; the constraints (one teacher, a phone, a free tier…).

## Decision
What was chosen, in a few lines.

## Rejected
The alternatives considered, each with why not.

## Consequences
What this costs or rules out, what to watch, and when to revisit.
```
