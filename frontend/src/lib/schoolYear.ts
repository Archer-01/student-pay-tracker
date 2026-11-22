import type { LedgerEntry } from "../api/types";

/**
 * A student's months laid out as the school year the teacher thinks in, September to August.
 * The student page shows these twelve tiles instead of a long table of rows that all look alike.
 */

export type TileState =
  /** Paid on time (or early, including months paid in advance). */
  | "paid"
  /** Paid, but late. */
  | "late"
  /** Due and not paid: money owed. */
  | "due"
  /** Not paid because the student was away that month: not owed. */
  | "away"
  /** Not due yet. */
  | "upcoming"
  /** Unpaid or coming, for a student free on purpose (decision 0011): never owed. */
  | "free"
  /** Nothing expected: before the student joined, or after they left. */
  | "none";

export type MonthTile = { month: string; state: TileState; entry?: LedgerEntry };

/** The school year a date falls in, named by the year its September is in. */
export function schoolYearStart(isoDate: string): number {
  const year = Number(isoDate.slice(0, 4));
  return Number(isoDate.slice(5, 7)) >= 9 ? year : year - 1;
}

function monthsOf(startYear: number): string[] {
  return Array.from({ length: 12 }, (_, i) => {
    const m = ((8 + i) % 12) + 1;
    const y = m >= 9 ? startYear : startYear + 1;
    return `${y}-${String(m).padStart(2, "0")}`;
  });
}

/**
 * Twelve tiles, September to August. The ledger already holds every month that has come due
 * (and any paid in advance); a month without an entry is either not due yet or not expected at
 * all. `enrolled` decides which: someone who has left is expected to pay nothing further. For a
 * student free on purpose, `free` turns what would be owed or coming into "free"; so does a month
 * that fell due while they were free (`waived`, decision 0011).
 */
export function monthTiles(
  entries: LedgerEntry[],
  startYear: number,
  {
    joinDate,
    today,
    enrolled,
    free = false,
  }: { joinDate: string; today: string; enrolled: boolean; free?: boolean },
): MonthTile[] {
  const byMonth = new Map(entries.map((e) => [e.expected_due_date.slice(0, 7), e]));
  const joinMonth = joinDate.slice(0, 7);
  const thisMonth = today.slice(0, 7);
  return monthsOf(startYear).map((month) => {
    const entry = byMonth.get(month);
    if (entry) {
      if (entry.paid_date !== null) {
        return { month, entry, state: (entry.days_late ?? 0) > 0 ? "late" : "paid" };
      }
      return { month, entry, state: entry.suspended ? "away" : free || entry.waived ? "free" : "due" };
    }
    if (month < joinMonth) return { month, state: "none" };
    // No entry and not in the past: this month's day hasn't come, or it's a later month.
    if (month >= thisMonth && enrolled) return { month, state: free ? "free" : "upcoming" };
    return { month, state: "none" };
  });
}

/** The school years worth showing: from the one the student joined in to the current one, or
 *  further if they have paid that far ahead. */
export function schoolYears(entries: LedgerEntry[], joinDate: string, today: string): number[] {
  const first = schoolYearStart(joinDate);
  const last = Math.max(
    schoolYearStart(today),
    ...entries.map((e) => schoolYearStart(e.expected_due_date)),
  );
  return Array.from({ length: Math.max(1, last - first + 1) }, (_, i) => first + i);
}
