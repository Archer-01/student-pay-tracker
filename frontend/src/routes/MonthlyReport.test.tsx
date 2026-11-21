import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { MonthlyReport } from "./MonthlyReport";

function row(over: Partial<Record<string, unknown>>) {
  return {
    student_id: 1, name: "Amina Benali", status: "active", fee: "240.00", collected: "240.00",
    cumulative_drift: 0, outstanding: "0.00", ...over,
  };
}

const noShare = { percent: "0", school: "0.00", teacher: "0.00" };

function report(rows: ReturnType<typeof row>[]) {
  return {
    year: 2026, month: 11, as_of: "2026-11-30", total_collected: "480.00", total_outstanding: "790.00",
    rows, share: noShare,
  };
}

const annual = { year: 2026, total_collected: "0.00", payments_count: 0, months: [], share: noShare };

beforeEach(() => {
  vi.spyOn(endpoints, "getAnnualReport").mockResolvedValue(annual as never);
});

const names = (list: HTMLElement) => within(list).getAllByRole("link").map((a) => a.textContent);

describe("Bilan › Mois, by student", () => {
  it("puts who hasn't paid first, most owed first, then who has, alphabetically", async () => {
    vi.spyOn(endpoints, "getMonthlyReport").mockResolvedValue(
      report([
        row({ student_id: 1, name: "Zineb Nouri" }),
        row({ student_id: 2, name: "Karim Bennis", collected: "0.00", outstanding: "190.00" }),
        row({ student_id: 3, name: "Amina Benali" }),
        row({ student_id: 4, name: "Youssef El Amrani", collected: "100.00", outstanding: "600.00" }),
      ]) as never,
    );
    renderWithProviders(<MonthlyReport />);

    const unpaid = await screen.findByRole("list", { name: "Not paid yet · 2" });
    expect(screen.getByRole("heading", { name: "Not paid yet · 2" })).toBeInTheDocument();
    expect(names(unpaid)).toEqual([
      expect.stringMatching(/Youssef El Amrani.*600\sDH/),
      expect.stringMatching(/Karim Bennis.*Paid nothing.*190\sDH/),
    ]);

    const paid = screen.getByRole("list", { name: "Paid · 2" });
    expect(screen.getByRole("heading", { name: "Paid · 2" })).toBeInTheDocument();
    expect(names(paid)).toEqual([
      expect.stringMatching(/Amina Benali.*Up to date/),
      expect.stringMatching(/Zineb Nouri.*Up to date/),
    ]);
  });

  it("leaves out a group with nobody in it", async () => {
    vi.spyOn(endpoints, "getMonthlyReport").mockResolvedValue(
      report([row({ student_id: 1, name: "Amina Benali" })]) as never,
    );
    renderWithProviders(<MonthlyReport />);
    await screen.findByRole("list", { name: "Paid · 1" });
    expect(screen.queryByText(/Not paid yet/)).not.toBeInTheDocument();
  });
});
