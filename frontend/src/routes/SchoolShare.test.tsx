import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { todayIso } from "../lib/dates";
import { SchoolShare } from "./SchoolShare";

function month(over: Partial<Record<string, unknown>>) {
  return {
    year: 2026, month: 10, collected: "1610.00", due: "402.50", handed_amount: null, handed_on: null,
    status: "due", remaining: "402.50", ...over,
  };
}

const share = {
  percent: "25",
  months: [
    month({ month: 11, collected: "940.00", due: "235.00", status: "running", remaining: "0" }),
    month({}),
    month({ month: 9, collected: "1760.00", due: "440.00", handed_amount: "390.00", handed_on: "2026-10-02", status: "short", remaining: "50.00" }),
    month({ year: 2026, month: 8, collected: "1200.00", due: "300.00", handed_amount: "300.00", handed_on: "2026-09-03", status: "handed", remaining: "0" }),
  ],
};

beforeEach(() => {
  vi.spyOn(endpoints, "getSchoolShare").mockResolvedValue(share as never);
});

describe("Bilan › École", () => {
  it("leads with the latest month to hand over, and marks it handed over today", async () => {
    const mark = vi.spyOn(endpoints, "markShareHandedOver").mockResolvedValue(share as never);
    renderWithProviders(<SchoolShare />);
    const due = await screen.findByRole("region", { name: /to hand over/i });
    expect(within(due).getByText(/October 2026/)).toBeInTheDocument();
    expect(within(due).getByText(/402\.50\sDH/)).toBeInTheDocument();
    await userEvent.click(within(due).getByRole("button", { name: /mark as handed over/i }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /mark as handed over/i }));
    expect(mark).toHaveBeenCalledWith(2026, 10, todayIso());
  });

  it("says where each month stands, in words", async () => {
    renderWithProviders(<SchoolShare />);
    const months = within(await screen.findByRole("list", { name: /months/i }));
    expect(months.getByText(/50\sDH short/)).toBeInTheDocument();
    expect(months.getByText(/handed over on/i)).toBeInTheDocument();
    expect(months.getByText(/to hand over/i)).toBeInTheDocument();
  });

  it("asks before undoing a handover", async () => {
    const unmark = vi.spyOn(endpoints, "unmarkShareHandedOver").mockResolvedValue(undefined as never);
    renderWithProviders(<SchoolShare />);
    await userEvent.click(await screen.findByRole("button", { name: /august 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /mark as not handed over/i }));
    expect(unmark).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /^mark not handed over$/i }));
    expect(unmark).toHaveBeenCalledWith(2026, 8);
  });

  it("says so when the school's share is turned off", async () => {
    vi.mocked(endpoints.getSchoolShare).mockResolvedValue({ percent: "0", months: [] } as never);
    renderWithProviders(<SchoolShare />);
    expect(await screen.findByText(/the school's share is turned off/i)).toBeInTheDocument();
  });
});
