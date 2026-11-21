# 0004. Northflank holds the only copy of the data; backups come later

- Status: Accepted
- Decided: 2026-11-20 · Recorded: 2026-11-21

## Context
Ardoise is deployed on Northflank's free tier: one container, SQLite files on its volume. The
teacher has no budget for anything else.

## Decision
For now the production volume is the only source of truth. The developer has told the teacher so
and keeps reminding them. Copies the developer takes by hand (`backup.db`, `local-prod/`) are
real student data: never committed (gitignored, and refused by `.claude/hooks/guard-bash.sh`).

## Rejected
- **Automated off-site backups now**: wanted, but postponed until the features settle; to be
  designed with whatever free storage is available.

## Consequences
- A lost volume loses the data since the last manual copy. This is the main known risk.
- Revisit soon: it is the next infrastructure topic once the current feature work is done.
