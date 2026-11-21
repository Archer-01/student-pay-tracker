# 0002. Prices are current, not historical

- Status: Accepted
- Decided: sprint 10, migration 0004 · Recorded: 2026-11-21

## Context
A student pays their pack's price, or a custom price. Prices change: a pack gets dearer, a
student moves pack or gets a discount.

## Decision
One current price per student (`custom_price`, else the pack's), read only through
`PricingService.price_of`. Changing it changes what is owed for months **not yet paid**. Money
already taken (`payment.amount`) never changes.

## Rejected
- **A price history** (price snapshots per period, or an append-only assignment table, as
  the sprint 10 plan first proposed): exact for past months, but three numbers per student to
  understand and edit instead of one, for a teacher who rarely changes prices mid-year.

## Consequences
- After a price change, older unpaid months are owed at the new price; the teacher accepted that.
- A payment can exceed today's price if it was made before a cut, so corrections only re-check a
  changed amount.
- Don't reintroduce snapshots without asking the developer.
