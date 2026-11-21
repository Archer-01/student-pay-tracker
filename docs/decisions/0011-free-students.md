# 0011. A student can be free on purpose

- Status: Accepted (replaces 0007)
- Decided: 2026-11-21 · Recorded: 2026-11-21

## Context
The teacher has set some students to 0 on purpose: they attend and pay nothing. The app treated
any student whose price came out at 0 as "Sans tarif" and listed them under « À vérifier » on
Accueil ("n'a pas de tarif : rien ne lui est facturé"), the same as a student nobody had priced
yet. 0007 framed this as recording 0 DH payments; with the teacher's case in hand, the price is
the right place: a free student owes nothing, so there is no payment to record.

## Decision
`PricingService.price_status` tells three cases apart, and the API sends it as `price_status`:

- **priced**: the student pays something;
- **free**: a price of 0 was set (an agreed price of 0, or a pack at 0). Shown as « Gratuit »,
  never chased, never listed as needing a price;
- **unset**: no pack and no agreed price. Still « Sans tarif » with the Accueil reminder, since
  that is a student nobody has priced yet.

Setting an agreed price of 0 when enrolling or editing a student asks first, so a 0 typed by
mistake doesn't silently stop the reminders. Payments keep their rule: positive, at most two
decimals.

## Rejected
- **Recording 0 DH payments month by month**: twelve entries a year to say what one price says,
  and each one a chance to forget a month.
- **Treating every price of 0 alike**: the reminder would either stay for students free on
  purpose, or go for students who simply haven't been priced.

## Consequences
- A free student counts toward nothing: not « Mensualités du mois », not « Cette semaine », not
  the money owed.
- To charge a free student again, set a price; their months from then on are owed like anyone's.
