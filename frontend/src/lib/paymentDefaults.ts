import type { LedgerEntry } from "../api/types";

/**
 * What the payment sheet opens with. Recording a payment used to start from three empty fields
 * even though the answer is nearly always the same: the oldest month still owed, today, and the
 * amount the student usually pays. These pick those defaults; the teacher only changes what's
 * different.
 */

export type MonthOption = {
  /** `YYYY-MM`, the `for_month` the API takes. */
  month: string;
  /** False for the upcoming month, i.e. paying in advance. */
  overdue: boolean;
};

const monthOf = (isoDate: string) => isoDate.slice(0, 7);

/**
 * Months that can be paid, oldest first; the first is the default. Unpaid months the student was
 * away for, or that fell due while they were free (decision 0011), are skipped (they are not owed), and the next scheduled month is offered last so a
 * payment in advance is one tap too.
 */
export function payableMonths(entries: LedgerEntry[], nextExpectedDate: string): MonthOption[] {
  const owed = entries
    .filter((e) => e.paid_date === null && !e.suspended && !e.waived)
    .sort((a, b) => a.cycle_number - b.cycle_number)
    .map((e) => ({ month: monthOf(e.expected_due_date), overdue: true }));
  const next = monthOf(nextExpectedDate);
  return owed.some((o) => o.month === next) ? owed : [...owed, { month: next, overdue: false }];
}

/** "240.00" → "240"; "199.50" stays. A string edit, so no float ever reaches the API. */
const trimCents = (amount: string) => amount.replace(/\.0+$/, "");

/**
 * The amount paid last time (by payment date), unless that is now above the price, in which
 * case the price. A first payment starts at the price. With no price at all there is nothing to
 * cap against: repeat the last payment, or leave the field empty.
 *
 * `Number` is used only to compare; the value returned is always one of the original strings.
 */
export function defaultAmount(entries: LedgerEntry[], monthlyPrice: string): string {
  const last = entries
    .filter((e) => e.paid_date !== null && e.amount !== null)
    .sort((a, b) => (a.paid_date! < b.paid_date! ? -1 : a.paid_date! > b.paid_date! ? 1 : a.cycle_number - b.cycle_number))
    .at(-1)?.amount;
  const priced = Number(monthlyPrice) > 0;
  if (!priced) return last ? trimCents(last) : "";
  if (last && Number(last) <= Number(monthlyPrice)) return trimCents(last);
  return trimCents(monthlyPrice);
}
