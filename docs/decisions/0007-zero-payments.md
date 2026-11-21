# 0007. A 0 DH payment is allowed on purpose

- Status: Replaced by 0011
- Decided: 2026-11-21 · Recorded: 2026-11-21

## Context
The teacher has recorded 0 DH payments for some students on purpose: a month they chose not to
charge. A review flagged amounts that end up at 0.00 as a bug; the developer confirmed 0 is a
legitimate payment. The code disagrees today: the API (`Field(gt=0)`) and
`PaymentService._check_amount` refuse an amount of 0.

## Decision
A month can be settled with a 0 DH payment. It counts as paid (on time or late by its date like
any payment) and is never a write-off.

## Not decided yet
How the app shows it: probably a clear choice when recording (« Mois offert »), shown as
« offert » on the tile and in the reports, rather than a bare 0 DH. To be agreed with the teacher
before building. Until then, don't "fix" existing 0 DH payments, and don't add checks that
reject them elsewhere.

## Consequences
- 0 DH months add nothing to what came in or to the school's share.
- When built: relax the positive-amount rule to ≥ 0 in the schema and the service, with tests,
  and update the "a payment is positive" invariant in `backend/CLAUDE.md`.
