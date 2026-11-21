import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { AnnualReport } from "./AnnualReport";

const share = (teacher: string, school: string) => ({ percent: "25", school, teacher });

beforeEach(() => {
  vi.spyOn(endpoints, "getAnnualReport").mockResolvedValue({
    year: 2026,
    total_collected: "1610.00",
    payments_count: 7,
    share: share("1207.50", "402.50"),
    months: Array.from({ length: 12 }, (_, i) =>
      i === 9
        ? { month: 10, collected: "1610.00", payments_count: 7, share: share("1207.50", "402.50") }
        : { month: i + 1, collected: "0.00", payments_count: 0, share: share("0.00", "0.00") },
    ),
  } as never);
});

describe("Bilan › Année, month by month", () => {
  it("gives each month one line: its name, how many payments, and the amount", async () => {
    renderWithProviders(<AnnualReport />);
    const months = await screen.findByRole("list", { name: "Months" });
    const items = within(months).getAllByRole("listitem");
    expect(items).toHaveLength(12);
    expect(items[9]).toHaveTextContent(/^October7 payments1,610 DH$/);
    // The share is in the Répartition card above and in Bilan › École, not on every month.
    expect(within(months).queryByText(/your share/i)).not.toBeInTheDocument();
  });

  it("mutes a month where nothing came in", async () => {
    renderWithProviders(<AnnualReport />);
    const months = await screen.findByRole("list", { name: "Months" });
    const items = within(months).getAllByRole("listitem");
    expect(items[0]).toHaveClass("text-muted");
    expect(items[9]).not.toHaveClass("text-muted");
  });
});
