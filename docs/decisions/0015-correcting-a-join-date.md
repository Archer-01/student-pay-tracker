# 0015. A mistyped join date can be corrected, until something depends on it

- Status: Accepted (qualifies the "join_date is immutable" rule in `backend/CLAUDE.md`)
- Decided: 2026-11-28 · Recorded: 2026-11-28

## Context
The join date is the anchor every due date and all lateness are computed from, so the app never
let it change. Aymen typed a student's join date wrong and recorded payments against it. He could
delete the payments, but nothing let him fix the date: the only way out was deleting the student.

## Decision
- The join date can be **corrected** (`PATCH /students/{id}` with `join_date`, « Date
  d'inscription » in « Modifier ») while nothing recorded was computed from it: no payment (its
  frozen due date and lateness), no write-off (its frozen amount). Otherwise the server refuses
  with a 409 saying which (`join_date_has_payments` / `join_date_has_writeoffs`), and the app
  locks the field with the reason.
- A **changed payment day** (« Changer le jour de paiement ») doesn't lock it: it is stored as a
  date, not from the join date, so it stays as it is. The new join date must only come before it,
  its own rule since it was made (`join_date_after_payment_day`).
- The app asks before saving a corrected date (« Les mois à payer seront recalculés à partir du
  … »), in the sheet, not with a browser pop-up.
- A correction makes the student read exactly as if the right date had been typed at enrolment.
  The first attendance period, and a free period opened at enrolment ("free from joining"), move
  with it; a free stretch opened later stays where it is. Everything else (tiles, what's owed,
  lateness) is computed from the date on every view. A property test pins this against a student
  enrolled with the right date, through price changes, a changed payment day, a leave and a
  return, and a payment.
- A corrected date after the student's first departure is refused (409, like the other
  attendance-ordering errors).
- Sending the same date is no change, so a plain save of a student with payments still works.

## Rejected
- **Moving the payments along with the date**: recomputing each payment's due date and lateness
  would rewrite recorded history, which the app never does. The teacher deletes the payments,
  corrects the date and records them again, as Aymen did.
- **Keeping the date locked**: the only fix left was deleting the student, losing everything else
  about them.

## Consequences
- The rule that a payment's due date and lateness are frozen still holds: they can't be stale,
  because no payment exists while the date moves.
- A return after a leave still never resets the join date: that is attendance, not a correction.
- A changed payment day replaced by a later one in the same month still counts: its date is
  stored, so a correction past it is refused even though no month falls on it any more. The app
  neither lists nor removes changed payment days, so the teacher can't clear it herself; the
  message names the date. Rare (two changes in one month, then a correction past the first).
- One known gap: with a join date typed **in the future**, a free stretch that ended before it
  covered no day and was deleted (decision 0014). Corrected to an earlier date, that stretch
  doesn't come back, so its months are owed. It takes a future typo, a price of 0 and a price
  again, all before the correction: rare enough to accept rather than keep empty periods.
