import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { act, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { ApiError } from "../api/client";
import { reportStored, resetConnectivity } from "../lib/connectivity";
import { usePaymentSheet } from "../lib/paymentSheetContext";
import { PaymentSheetProvider } from "./PaymentSheet";

/** Owes October; paid 200 for September. */
const student = {
  id: 13, full_name: "Amina Benali", monthly_price: "250.00", price_status: "priced", months_overdue: 1,
  amount_owed: "250.00", next_expected_date: "2026-11-05",
};
const ledger = {
  student_id: 13, as_of: "2026-10-20", cumulative_drift: 0,
  entries: [
    { cycle_number: 0, expected_due_date: "2026-09-05", paid_date: "2026-09-05", days_late: 0, amount: "200.00", cumulative_drift: 0, suspended: false, waived: false },
    { cycle_number: 1, expected_due_date: "2026-10-05", paid_date: null, days_late: null, amount: null, cumulative_drift: 0, suspended: false, waived: false },
  ],
};

/** A screen that opens the sheet and shows the refresh counter every money screen depends on. */
function Screen() {
  const sheet = usePaymentSheet();
  return (
    <>
      <button type="button" onClick={() => sheet.open(13)}>Take a payment</button>
      <output aria-label="version">{sheet.version}</output>
    </>
  );
}

beforeEach(() => {
  vi.spyOn(endpoints, "getStudent").mockResolvedValue(student as never);
  vi.spyOn(endpoints, "getLedger").mockResolvedValue(ledger as never);
  vi.spyOn(endpoints, "recordPayment").mockResolvedValue({ student_id: 13, cycle_number: 1, amount: "200.00" } as never);
  vi.spyOn(endpoints, "deletePayment").mockResolvedValue(undefined);
});

afterEach(() => {
  resetConnectivity();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function recordOne(user = userEvent.setup()) {
  renderWithProviders(
    <PaymentSheetProvider>
      <Screen />
    </PaymentSheetProvider>,
  );
  await user.click(screen.getByRole("button", { name: "Take a payment" }));
  await user.click(await screen.findByRole("button", { name: /^record 200\sDH$/i }));
  await screen.findByText(/payment recorded: 200\sDH for Amina Benali/i);
  return user;
}

const version = () => screen.getByLabelText("version").textContent;

describe("PaymentSheetProvider", () => {
  it("offers to undo the payment just recorded, and undoing it refreshes every screen", async () => {
    const user = await recordOne();
    expect(version()).toBe("1");

    await user.click(screen.getByRole("button", { name: "Undo" }));

    expect(endpoints.deletePayment).toHaveBeenCalledWith(13, 1);
    expect(await screen.findByText("Payment undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    expect(version()).toBe("2");
  });

  it("says why when the payment could not be undone, and leaves the screens as they are", async () => {
    vi.mocked(endpoints.deletePayment).mockRejectedValue(new ApiError(404, "No payment for that month", "x"));
    const user = await recordOne();

    await user.click(screen.getByRole("button", { name: "Undo" }));

    expect(await screen.findByText("No payment for that month")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    expect(version()).toBe("1");
  });

  it("offers no undo once the app is read only", async () => {
    await recordOne();
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();

    act(() => reportStored("2026-11-21T10:00:00Z"));

    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    expect(screen.getByText(/payment recorded/i)).toBeInTheDocument();
  });

  it("keeps the undo on screen for about six seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await recordOne(userEvent.setup({ advanceTimers: vi.advanceTimersByTime }));

    act(() => vi.advanceTimersByTime(5200)); // the plain confirmation would be gone by 5 s
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(900));
    await waitFor(() => expect(screen.queryByText(/payment recorded/i)).toBeNull());
  });

  it("keeps the message up while the undo is on its way", async () => {
    vi.mocked(endpoints.deletePayment).mockReturnValue(new Promise(() => {}));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = await recordOne(userEvent.setup({ advanceTimers: vi.advanceTimersByTime }));

    await user.click(screen.getByRole("button", { name: "Undo" }));
    act(() => vi.advanceTimersByTime(10_000));

    expect(screen.getByText(/payment recorded/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  });
});

describe("choosing who paid", () => {
  it("leaves out students free on purpose: they can't be sent a payment", async () => {
    vi.spyOn(endpoints, "listStudents").mockResolvedValue([
      { ...student, id: 13, full_name: "Amina Benali" },
      { ...student, id: 14, full_name: "Imrane Free", price_status: "free", months_overdue: 0, amount_owed: "0.00" },
    ] as never);
    function Picker() {
      const sheet = usePaymentSheet();
      return <button type="button" onClick={() => sheet.open()}>Take any payment</button>;
    }
    renderWithProviders(
      <PaymentSheetProvider>
        <Picker />
      </PaymentSheetProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Take any payment" }));
    expect(await screen.findByText("Amina Benali")).toBeInTheDocument();
    expect(screen.queryByText("Imrane Free")).not.toBeInTheDocument();
  });

  it("says why when the search finds only students who pay nothing", async () => {
    vi.spyOn(endpoints, "listStudents").mockResolvedValue([
      { ...student, id: 14, full_name: "Imrane Free", price_status: "free", months_overdue: 0, amount_owed: "0.00" },
    ] as never);
    function Picker() {
      const sheet = usePaymentSheet();
      return <button type="button" onClick={() => sheet.open()}>Take any payment</button>;
    }
    renderWithProviders(
      <PaymentSheetProvider>
        <Picker />
      </PaymentSheetProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Take any payment" }));
    expect(await screen.findByText("This student pays nothing: there is nothing to record.")).toBeInTheDocument();
  });
});
