import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { LeaversWithDebt } from "./LeaversWithDebt";

const leaver = {
  student: {
    id: 5, first_name: "Fatima Zahra", last_name: null, full_name: "Fatima Zahra",
    phone: "+212633445566", is_repeating: false, join_date: "2023-11-01", status: "inactive",
    class_id: null, school_class: null, pack_id: null, pack: null,
    custom_price: null, price_note: null, created_at: "",
  },
  left_on: "2024-01-31", amount_owed: "170.00", months_owed: 1,
  left_with_debt: true, written_off: null,
};

beforeEach(() => {
  vi.spyOn(endpoints, "listLeaversWithDebt").mockResolvedValue({
    leavers: [leaver], total_owed: "170.00",
  } as never);
  vi.spyOn(endpoints, "writeOffDebt").mockResolvedValue({
    id: 1, amount: "170.00", reason: "moved",
  } as never);
});

describe("LeaversWithDebt", () => {
  it("lists who left owing what", async () => {
    renderWithProviders(<LeaversWithDebt />);
    expect(await screen.findByRole("link", { name: "Fatima Zahra" })).toBeInTheDocument();
    expect(screen.getAllByText("170.00").length).toBeGreaterThan(0);
  });

  it("invites action when nobody owes", async () => {
    vi.mocked(endpoints.listLeaversWithDebt).mockResolvedValue({
      leavers: [], total_owed: "0",
    } as never);
    renderWithProviders(<LeaversWithDebt />);
    expect(await screen.findByText(/nobody has left owing money/i)).toBeInTheDocument();
  });

  it("says a write-off is not a payment before asking for one", async () => {
    // The shortcut this wording exists to prevent is recording a fake payment to clear the list.
    renderWithProviders(<LeaversWithDebt />);
    await userEvent.click(await screen.findByRole("button", { name: /write off/i }));
    expect(screen.getByText(/not a payment/i)).toBeInTheDocument();
  });

  it("refuses to write off without a reason", async () => {
    renderWithProviders(<LeaversWithDebt />);
    await userEvent.click(await screen.findByRole("button", { name: /write off/i }));
    await userEvent.click(screen.getByRole("button", { name: /write off 170/i }));
    expect(endpoints.writeOffDebt).not.toHaveBeenCalled();
  });

  it("writes off with a reason and refreshes the list", async () => {
    renderWithProviders(<LeaversWithDebt />);
    await userEvent.click(await screen.findByRole("button", { name: /write off/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "moved abroad");
    await userEvent.click(screen.getByRole("button", { name: /write off 170/i }));
    await waitFor(() =>
      expect(endpoints.writeOffDebt).toHaveBeenCalledWith(5, { reason: "moved abroad" }),
    );
    expect(endpoints.listLeaversWithDebt).toHaveBeenCalledTimes(2);
  });
});
