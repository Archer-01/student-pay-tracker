# 0008. The CLI will be reworked; its known bugs wait for it

- Status: Accepted
- Decided: 2026-11-21 · Recorded: 2026-11-21

## Context
The `ardoise` CLI is the developer's admin tool (accounts, corrections, imports), built in sprint
4 before the API. A review found that it skips checks the API does, because those live only in
the API's request schemas: `payments record` and `payments edit` accept a paid date in the
future, which inflates drift (5 → 1726 days in a test).

## Decision
The developer will rework the CLI after the current quality work. Its known bugs are fixed as
part of that rework, not one by one now.

## Consequences
- Until then, use the CLI with care for payments; the app and the API are not affected.
- In the rework: move "no future paid date" and the amount checks (at most two decimals; ≥ 0
  per 0007) into `PaymentService`, so the API, the CLI and the app share one rule, with tests
  at the service level.
