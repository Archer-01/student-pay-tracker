# What each screen does

How the screens behave and why, screen by screen. `../CLAUDE.md` holds the rules every screen
follows; this file is what to read before changing one of them, and what to update after.

## Taking a payment

There is one payment sheet for the whole app, provided by `Layout` (`PaymentSheetProvider` in
`src/components/PaymentSheet.tsx`). Open it with `usePaymentSheet().open(studentId?)`; without an
id it starts on a student picker that lists the students who owe first.

The sheet opens filled in (`src/lib/paymentDefaults.ts`, with its own tests):

- **Month**: the oldest unpaid month that is actually owed (months the student was away for are
  skipped), with the next month offered last for paying in advance.
- **Amount**: what the student paid last time, unless that is above their current price, in
  which case the price. Not the price by default: several students pay less than their listed
  price, and starting there invites the over-payment typo the backend cap exists for.
- **Date**: today.

The confirmation after a payment carries **Annuler** for about six seconds: it deletes the
payment just recorded and announces "Paiement annulé" through `changed()`. Not offered offline.

## Accueil

Top to bottom:

1. the month as a title;
2. two figures: what came in this month (all cash, back payments included, with the teacher's
   part under it) and what is owed today ("Impayés aujourd'hui");
3. **Mensualités du mois**: this month's fees against what has been paid toward them, as a
   count of students and a bar (hidden in a month where nobody is due);
4. the pay button;
5. **Encaissé aujourd'hui**: the payments recorded today (back-dated ones included, since those
   are the typos worth catching), each linking to the student page on that month
   (`?month=YYYY-MM`) so a typo is one tap from Modifier;
6. anything needing attention ("À vérifier", including last month's school share still to hand
   over);
7. **À relancer** (months unpaid and class only);
8. **Cette semaine**: the unpaid dues of the next seven days, soonest first, said as
   "aujourd'hui", "demain" or the day (hidden when empty);
9. the link to former students who left owing.

The server computes the two new lists (`this_month`, `due_this_week` on the dashboard summary)
from the same override-aware schedule as the student page.

## Élèves

The filters sit on wrapping rows, all visible on a phone: "Tous · n", "Impayés · n",
"Ponctualité", then the classes and "Anciens". Active students are fetched once and filtered by
class here, so the counts don't depend on the chip selected.

Enrolling a student pre-selects the pack when the chosen class's level has exactly one offered
pack ("Choisi d'après la classe"), until the teacher touches the pack field.

A student's pill reads « Gratuit » when their price was set to 0 on purpose, and « Sans tarif »
when no price was set at all (decision 0011). Setting an agreed price of 0, when enrolling or in
the edit form, asks « … C'est voulu ? » first; a student already free isn't asked again.

Questions before a save (a price of 0) are asked in the form itself (`ConfirmBox`, amber): the
form's buttons give way to « Non, revenir » / « Oui, enregistrer » (« Oui, inscrire » on
enrolment) until answered. Not « Annuler »: that word already closes the sheet, and this one only
goes back to the form.

## The student page

The school year is twelve tiles, September to August (`src/lib/schoolYear.ts`, with its own
tests): paid, paid late, owed, away (not owed), not yet due, or nothing expected (before joining,
after leaving). The ledger already holds every month that has come due plus any paid in advance,
so a month without an entry is either upcoming or not expected; whether the student is still
enrolled decides which. Tapping an owed tile opens the payment sheet on that month.

`/students/:id?month=YYYY-MM` opens that month's sheet directly (turning to its school year),
then drops the parameter so a refresh doesn't reopen it; Accueil's "Encaissé aujourd'hui" rows
use it.

Tapping a paid tile shows what was recorded and, online, lets a typo be fixed:
**Modifier ce paiement** (`EditPaymentForm`: amount and date, sending only what changed) or
**Supprimer ce paiement**, which asks first in the same sheet and says the month will be owed
again. There is no "move to another month": that is delete, then record the right month, and the
confirmation says so. Both announce themselves through `usePaymentSheet().changed(message)`,
which bumps the same `version` as a recorded payment, so every screen refreshes and the same
toast appears.

**Ponctualité** (one row in Détails, and a chip on the students list, latest payers first): the
server's `average_days_late` over the student's last six payments, read as À l'heure (0–2 days),
Un peu tard (3–7) or Souvent tard (8+) by `lib/punctuality.ts`, with the cumulative total beside
it ("Retard moyen 2 j · 34 j au total"). It reads the frozen lateness of payments; it is not drift
and changes nothing.

The status card of a free student says « Gratuit » (nothing is ever asked of them) with
« Modifier le tarif », and their unpaid and coming months read « gratuit » on the tiles (and on
the PDF); one with no price says « Sans tarif » with « Choisir un pack ». Once a free student is
given a price, the months that fell due while they were free stay « gratuit » (`waived` in the
ledger, decision 0014), say so when tapped, and are never offered for payment.

Under the status card sits the teacher's **note** on the student (`student.note`, up to 500
characters), or a quiet "Ajouter une note" link when there is none; both open `NoteSheet`, a sheet
with just the note (the full edit form keeps the field too). It is private: it never goes on a
PDF, since those are sent to parents.

The departure/return action follows the **enrolment periods**, not `status`: a student set to
inactive by hand still has an open period, and only "Marquer comme parti" fixes that. The edit
form has no status field for the same reason.

## Bilan › Mois and Année

Mois lists students in two groups, **Pas encore payé** (most owed first) then **Ont payé**, each
with its count. Année is one line per month: the month, the number of payments, the amount; the
school share lives in the Répartition card and in Bilan › École.

## Bilan › École

The school's share of each month, and whether it was handed over (`routes/SchoolShare.tsx`). It
leads with the latest month still to hand over and **Marquer comme remis** (today, or another
day); below, every month in words: "Remis le 3 nov.", "Il manque 50 DH" (a payment recorded after
the month was settled), "À remettre", "Rien à remettre". A handed-over month can have its date
changed or the handover undone (asked first). With two or more months outstanding, the card adds
« Au total : 3 412,50 DH à remettre pour 7 mois » (summed by the server) and **Tout marquer comme
remis**, a sheet that says how many months and how much, takes the date, and marks every ended
month still due or short in one go, for months already handed over in cash. The total shown goes
with the request: if a payment moved it meanwhile, the server refuses, the sheet says so and shows
the new total, and nothing is marked until that one is confirmed. While last month's
share is outstanding, Accueil's "À vérifier" box says so and links here. The tab is hidden when
the share is 0 %.

## Réglages

Classes and packs (`/settings/classes`, `/settings/packs`), language, appearance, **Hors ligne**
(when the last full offline copy was made) and sign-out.

**A pack is one name at one level**, listed and edited on its own (`routes/PacksList.tsx`).
There is no grouping of packs across levels any more: the teacher names each pack for its level
("Pack TC Scientifique"), and an offer × level grid was mostly empty cells. A pack's level is
locked once a student has it (the server refuses it too).
