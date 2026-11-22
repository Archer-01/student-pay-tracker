import { describe, expect, it } from "vitest";
import type { LedgerEntry } from "../api/types";
import { defaultAmount, payableMonths } from "./paymentDefaults";

function entry(partial: Partial<LedgerEntry> & Pick<LedgerEntry, "cycle_number" | "expected_due_date">): LedgerEntry {
  return {
    paid_date: null,
    days_late: null,
    amount: null,
    cumulative_drift: 0,
    suspended: false,
    waived: false,
    ...partial,
  };
}

const paid = (cycle: number, due: string, amount: string, paidOn = due) =>
  entry({ cycle_number: cycle, expected_due_date: due, paid_date: paidOn, amount, days_late: 0 });
const unpaid = (cycle: number, due: string, suspended = false) =>
  entry({ cycle_number: cycle, expected_due_date: due, suspended });

describe("payableMonths", () => {
  it("offers unpaid months oldest first, the oldest being the default", () => {
    const entries = [paid(0, "2026-09-05", "240"), unpaid(1, "2026-10-05"), unpaid(2, "2026-11-05")];
    expect(payableMonths(entries, "2026-12-05")).toEqual([
      { month: "2026-10", overdue: true },
      { month: "2026-11", overdue: true },
      { month: "2026-12", overdue: false },
    ]);
  });

  it("skips months the student was away for: they are not owed", () => {
    const entries = [unpaid(0, "2026-09-05", true), unpaid(1, "2026-10-05")];
    expect(payableMonths(entries, "2026-11-05").map((m) => m.month)).toEqual(["2026-10", "2026-11"]);
  });

  it("skips months that fell due while the student was free: they stay free", () => {
    const entries = [
      entry({ cycle_number: 0, expected_due_date: "2026-09-05", waived: true }),
      unpaid(1, "2026-10-05"),
    ];
    expect(payableMonths(entries, "2026-11-05").map((m) => m.month)).toEqual(["2026-10", "2026-11"]);
  });

  it("offers the next month in advance when everything is paid", () => {
    const entries = [paid(0, "2026-09-05", "240"), paid(1, "2026-10-05", "240")];
    expect(payableMonths(entries, "2026-11-05")).toEqual([{ month: "2026-11", overdue: false }]);
  });

  it("does not list the next month twice when it is already due today", () => {
    const entries = [paid(0, "2026-10-05", "240"), unpaid(1, "2026-11-05")];
    expect(payableMonths(entries, "2026-11-05")).toEqual([{ month: "2026-11", overdue: true }]);
  });

  it("works for a brand-new student with nothing due yet", () => {
    expect(payableMonths([], "2026-11-20")).toEqual([{ month: "2026-11", overdue: false }]);
  });
});

describe("defaultAmount", () => {
  it("starts at what the student paid last time", () => {
    // Listed at 250, pays 200: starting at the price would invite the typo the cap exists for.
    const entries = [paid(0, "2026-09-05", "200.00"), paid(1, "2026-10-05", "200.00")];
    expect(defaultAmount(entries, "250.00")).toBe("200");
  });

  it("uses the most recent payment by date, not by month", () => {
    const entries = [paid(1, "2026-10-05", "150.00", "2026-10-06"), paid(0, "2026-09-05", "200.00", "2026-11-02")];
    expect(defaultAmount(entries, "250.00")).toBe("200");
  });

  it("falls back to the price when the last payment is above it (the price was cut)", () => {
    expect(defaultAmount([paid(0, "2026-09-05", "300.00")], "240.00")).toBe("240");
  });

  it("uses the price for a first payment", () => {
    expect(defaultAmount([], "240.00")).toBe("240");
  });

  it("keeps cents when there are some, and sends the original string otherwise untouched", () => {
    expect(defaultAmount([paid(0, "2026-09-05", "199.50")], "240.00")).toBe("199.50");
  });

  it("with no price, repeats the last payment, or leaves the field empty", () => {
    expect(defaultAmount([paid(0, "2026-09-05", "180.00")], "0.00")).toBe("180");
    expect(defaultAmount([], "0.00")).toBe("");
  });
});
