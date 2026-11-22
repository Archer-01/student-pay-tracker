import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { act, screen, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { todayIso } from "../lib/dates";
import { ApiError } from "../api/client";
import { reportStored, resetConnectivity } from "../lib/connectivity";
import { SchoolShare } from "./SchoolShare";

function month(over: Partial<Record<string, unknown>>) {
  return {
    year: 2026, month: 10, collected: "1610.00", due: "402.50", handed_amount: null, handed_on: null,
    status: "due", remaining: "402.50", ...over,
  };
}

const share = {
  percent: "25",
  // October due (402.50) and September short (50): the server's sum, never the browser's.
  outstanding: "452.50",
  outstanding_months: 2,
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

  it("adds up the months still to hand over, and can mark them all after saying what it will do", async () => {
    const markAll = vi.spyOn(endpoints, "handOverAllShare").mockResolvedValue(share as never);
    renderWithProviders(<SchoolShare />);
    const due = await screen.findByRole("region", { name: /to hand over/i });
    expect(within(due).getByText(/In all: 452\.50\sDH to hand over for 2 months/)).toBeInTheDocument();

    await userEvent.click(within(due).getByRole("button", { name: "Mark all as handed over" }));
    const sheet = within(screen.getByRole("dialog"));
    expect(sheet.getByText(/The 2 months still to hand over \(452\.50\sDH\)/)).toBeInTheDocument();
    expect(markAll).not.toHaveBeenCalled();
    await userEvent.click(sheet.getByRole("button", { name: "Mark the 2 months as handed over" }));
    // The total the teacher was shown goes with it: the server refuses if it has moved since.
    expect(markAll).toHaveBeenCalledWith(todayIso(), "452.50");
  });

  it("shows the new total when it changed meanwhile, and marks only once it is confirmed", async () => {
    const markAll = vi
      .spyOn(endpoints, "handOverAllShare")
      .mockRejectedValueOnce(new ApiError(409, "The amount to hand over has changed: it is now 502.50 DH.", "share_outstanding_changed"))
      .mockResolvedValue(share as never);
    renderWithProviders(<SchoolShare />);
    const due = await screen.findByRole("region", { name: /to hand over/i });
    await userEvent.click(within(due).getByRole("button", { name: "Mark all as handed over" }));
    // A payment came in meanwhile: the page now reads a larger total.
    vi.mocked(endpoints.getSchoolShare).mockResolvedValue({ ...share, outstanding: "502.50" } as never);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark the 2 months as handed over" }));

    const sheet = within(screen.getByRole("dialog"));
    expect(await sheet.findByText(/it is now 502\.50 DH/)).toBeInTheDocument();
    expect(await sheet.findByText(/The 2 months still to hand over \(502\.50\sDH\)/)).toBeInTheDocument();
    await userEvent.click(sheet.getByRole("button", { name: "Mark the 2 months as handed over" }));
    expect(markAll).toHaveBeenLastCalledWith(todayIso(), "502.50");
  });

  it("can't mark everything once the app goes offline, even with the sheet open", async () => {
    renderWithProviders(<SchoolShare />);
    const due = await screen.findByRole("region", { name: /to hand over/i });
    await userEvent.click(within(due).getByRole("button", { name: "Mark all as handed over" }));
    act(() => reportStored("2026-11-14T09:41:00"));
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark the 2 months as handed over" })).toBeDisabled();
    act(() => resetConnectivity());
  });

  it("shows no total when a single month is outstanding", async () => {
    vi.mocked(endpoints.getSchoolShare).mockResolvedValue({
      ...share,
      outstanding: "402.50",
      outstanding_months: 1,
    } as never);
    renderWithProviders(<SchoolShare />);
    await screen.findByRole("region", { name: /to hand over/i });
    expect(screen.queryByText(/in all/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark all as handed over" })).not.toBeInTheDocument();
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
    // The confirm button, in the red box, says the same as the link that opened it.
    const confirm = within(screen.getByRole("dialog")).getAllByRole("button", { name: /mark as not handed over/i });
    await userEvent.click(confirm[confirm.length - 1]!);
    expect(unmark).toHaveBeenCalledWith(2026, 8);
  });

  it("says so when the school's share is turned off", async () => {
    vi.mocked(endpoints.getSchoolShare).mockResolvedValue({ percent: "0", months: [] } as never);
    renderWithProviders(<SchoolShare />);
    expect(await screen.findByText(/the school's share is turned off/i)).toBeInTheDocument();
  });
});
