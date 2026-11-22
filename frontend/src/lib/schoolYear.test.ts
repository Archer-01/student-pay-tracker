import { describe, expect, it } from "vitest";
import type { LedgerEntry } from "../api/types";
import { monthTiles, schoolYearStart, schoolYears } from "./schoolYear";

function entry(cycle: number, due: string, over: Partial<LedgerEntry> = {}): LedgerEntry {
  return {
    cycle_number: cycle, expected_due_date: due, paid_date: null, days_late: null, amount: null,
    cumulative_drift: 0, suspended: false, waived: false, ...over,
  };
}
const paid = (cycle: number, due: string, paidOn: string, daysLate = 0) =>
  entry(cycle, due, { paid_date: paidOn, days_late: daysLate, amount: "200.00" });

const states = (tiles: ReturnType<typeof monthTiles>) => tiles.map((t) => `${t.month}:${t.state}`);

describe("schoolYearStart", () => {
  it.each([
    ["2026-09-01", 2026],
    ["2026-12-31", 2026],
    ["2027-01-15", 2026],
    ["2027-08-31", 2026],
  ])("%s belongs to the school year starting in %i", (date, year) => {
    expect(schoolYearStart(date)).toBe(year);
  });
});

describe("monthTiles", () => {
  const base = { joinDate: "2026-09-05", today: "2026-11-14", enrolled: true };

  it("lays out September to August, one tile per month", () => {
    const tiles = monthTiles([], 2026, base);
    expect(tiles.map((t) => t.month)).toEqual([
      "2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02",
      "2027-03", "2027-04", "2027-05", "2027-06", "2027-07", "2027-08",
    ]);
  });

  it("tells paid, paid late, owed and not-yet-due apart", () => {
    const entries = [paid(0, "2026-09-05", "2026-09-05"), paid(1, "2026-10-05", "2026-10-13", 8), entry(2, "2026-11-05")];
    expect(states(monthTiles(entries, 2026, base)).slice(0, 4)).toEqual([
      "2026-09:paid", "2026-10:late", "2026-11:due", "2026-12:upcoming",
    ]);
  });

  it("keeps the entry on the tile, for the month's details", () => {
    const tiles = monthTiles([paid(1, "2026-10-05", "2026-10-13", 8)], 2026, base);
    expect(tiles[1]!.entry?.paid_date).toBe("2026-10-13");
  });

  it("shows a month paid in advance as paid", () => {
    const entries = [paid(0, "2026-09-05", "2026-09-05"), paid(1, "2026-10-05", "2026-10-05"), paid(2, "2026-11-05", "2026-11-03"), paid(3, "2026-12-05", "2026-11-03")];
    expect(monthTiles(entries, 2026, base)[3]!.state).toBe("paid");
  });

  it("marks months the student was away for, which are not owed", () => {
    const entries = [paid(0, "2026-09-05", "2026-09-05"), entry(1, "2026-10-05", { suspended: true })];
    expect(monthTiles(entries, 2026, base)[1]!.state).toBe("away");
  });

  it("keeps months that fell due while free as free once the student has a price", () => {
    const entries = [entry(0, "2026-09-05", { waived: true }), entry(1, "2026-10-05", { waived: true }), entry(2, "2026-11-05")];
    expect(states(monthTiles(entries, 2026, base)).slice(0, 4)).toEqual([
      "2026-09:free", "2026-10:free", "2026-11:due", "2026-12:upcoming",
    ]);
  });

  it("shows a free student's unpaid and coming months as free, and paid ones as paid", () => {
    // Free on purpose (decision 0011): nothing is owed or coming.
    const entries = [
      paid(0, "2026-09-05", "2026-09-05"),
      entry(1, "2026-10-05", { suspended: true }),
      entry(2, "2026-11-05"),
    ];
    expect(states(monthTiles(entries, 2026, { ...base, free: true })).slice(0, 5)).toEqual([
      "2026-09:paid", "2026-10:away", "2026-11:free", "2026-12:free", "2027-01:free",
    ]);
  });

  it("leaves months before the student joined blank", () => {
    const tiles = monthTiles([], 2026, { ...base, joinDate: "2026-11-02" });
    expect(states(tiles).slice(0, 3)).toEqual(["2026-09:none", "2026-10:none", "2026-11:upcoming"]);
  });

  it("treats this month as not yet due when its day hasn't come", () => {
    // Joined on the 26th: on the 14th of the next month, that month's payment isn't due yet.
    const tiles = monthTiles([paid(0, "2026-10-26", "2026-11-03", 8)], 2026, { ...base, joinDate: "2026-10-26" });
    expect(tiles[2]!.state).toBe("upcoming");
  });

  it("expects nothing more from a student who has left", () => {
    const tiles = monthTiles([paid(0, "2026-09-05", "2026-09-05")], 2026, { ...base, enrolled: false });
    expect(tiles[3]!.state).toBe("none");
  });
});

describe("schoolYears", () => {
  it("runs from the year the student joined to the current one", () => {
    expect(schoolYears([], "2025-03-10", "2026-11-14")).toEqual([2024, 2025, 2026]);
  });

  it("includes next year when a payment was made that far ahead", () => {
    const entries = [paid(12, "2027-09-05", "2026-11-14")];
    expect(schoolYears(entries, "2026-09-05", "2026-11-14")).toEqual([2026, 2027]);
  });
});
