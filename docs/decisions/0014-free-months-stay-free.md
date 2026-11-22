# 0014. Months that were free stay free, and a free student pays nothing

- Status: Accepted (builds on 0011)
- Decided: 2026-11-22 · Recorded: 2026-11-22

## Context
0011 made "free on purpose" a price status, but the ledger has no history of prices (0002): it
prices every unpaid month at today's price. So giving a free student a price billed every month
they had been free, back to the day they joined, and a free student could be sent a payment of
any size, since the cap on a payment is the price and theirs was 0. A domain review found both,
and the developer chose the answers below.

A first version stored one date, "billed from". The second review showed one date can't say
when a student *became* free. A 0 typed by mistake and fixed the same day erased months of real
debt (a leaver's too) with no write-off, and a free pack given a price still billed its students
back.

## Decision
- **Free periods.** Each stretch of being free is a row in `free_period` (from, to), opened when
  a student becomes free and closed when they get a price or lose theirs (« Sans tarif »). This
  happens whether the change comes from the student's own price or their pack's.
  `FreePeriodService.follow_price` is the one rule, called after every price change. An
  enrolment at 0 is free from the join date, and so is a student whose price is corrected to 0 on
  the day they were entered (`student.entered_on`).
- **What it waives.** An unpaid month due on a day in [from, to) is `waived` in the ledger: not
  owed, never chased, shown « gratuit » on the tiles and the PDF. Months outside every period
  are owed as before. A period closed on the day it was opened (`opened_on`) was a mistake fixed
  at once and is deleted, even when it was backdated to the join date: a 0 typed by mistake, at
  enrolment or later, erases nothing. A paid month is never waived, so drift is untouched. A
  student nobody had priced yet ("unset") owes their months once priced, as before.
- **A free student can't be sent a payment.** `PaymentService` refuses it
  (`payment_student_free`, « Cet élève ne paie rien : modifiez son tarif… »). To take money from
  them, give them a price first.
- **An old payment of a free student can be lowered, never raised**
  (`payment_raised_for_free_student`). With no price left to compare with, its recorded amount
  is the cap.

## Rejected
- **Billing the free months back**: what a free student "owes" for the year they were free is
  money nobody ever asked for, and the teacher would see red tiles for it.
- **One "billed from" date** (the first version): see the context above.
- **Two dates (free since, billed from)**: one stretch only. A second free stretch forgets the
  first one's months.
- **A full price history**: 0002 still holds. Only whether a student was free needs history.
- **Letting a free student pay, or raise an old payment, with no cap**: a typo (3000 for 300)
  would go through unchecked, the one case where the cap is the only guard.

## Consequences
- Migration 0012 gives every student free at the upgrade an open period from their join date.
  Its downgrade drops the periods, so formerly free months would count as owed again.
- Periods are written by the service, never by hand or by the API.
- Paying a waived (or suspended) month directly through the API is still accepted, as for
  suspended months before. The app never offers it.
- A period covers the day it starts: a student set to 0 on a due day and priced again the next
  day has that month free. Accepted: [from, to) is the plainest rule, and a slip fixed on the
  same day leaves nothing.
- A property test drives the service with random price histories and checks that a mistake
  undone the same day, anywhere in them, changes no month.
