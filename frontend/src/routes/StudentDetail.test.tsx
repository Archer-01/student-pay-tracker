import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { act, screen, waitFor } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { PaymentSheetProvider } from "../components/PaymentSheet";
import { StudentDetail } from "./StudentDetail";
import { reportStored, resetConnectivity } from "../lib/connectivity";

function student(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 5, first_name: "Fatima", last_name: "Zahra", full_name: "Fatima Zahra", phone: null,
    is_repeating: false, join_date: "2026-09-01", status: "active", class_id: null, school_class: null,
    pack_id: null, pack: null, custom_price: "200.00", price_note: null, note: null, created_at: "2026-09-01T00:00:00",
    cumulative_drift: 0, months_overdue: 0, amount_owed: "0.00", monthly_price: "200.00",
    next_expected_date: "2026-12-01", payments_count: 0, total_paid: "0.00", first_payment_date: null,
    average_days_late: null,
    as_of: "2026-11-14", ...over,
  };
}

const ledger = { student_id: 5, as_of: "2026-11-14", cumulative_drift: 0, entries: [] };
const open = { id: 1, student_id: 5, entry_date: "2026-09-01", leave_date: null, leave_reason: null };
const closed = { ...open, leave_date: "2026-10-15" };

async function openMenu() {
  await userEvent.click(await screen.findByRole("button", { name: /more actions/i }));
}

/** The address bar, as text, so a test can see what the page did to the URL. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

function renderPage(route = "/students/5") {
  renderWithProviders(
    <PaymentSheetProvider>
      <Routes>
        <Route path="/students/:id" element={<StudentDetail />} />
      </Routes>
      <Location />
    </PaymentSheetProvider>,
    { route },
  );
}

beforeEach(() => {
  vi.spyOn(endpoints, "getLedger").mockResolvedValue(ledger as never);
});

describe("StudentDetail departure button", () => {
  it("offers to record a departure for an attending student", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    await openMenu();
    expect(await screen.findByRole("button", { name: /mark as left/i })).toBeInTheDocument();
  });

  it("offers a return once the departure is recorded", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ status: "inactive" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([closed] as never);
    renderPage();
    await openMenu();
    expect(await screen.findByRole("button", { name: /mark as returned/i })).toBeInTheDocument();
  });

  it("follows the enrolment, not the status: an 'Inactif' student with no departure date can still be marked as left", async () => {
    // What the dashboard's "sans date de départ" warning links to. Status says inactive, but the
    // enrolment is still open, so a return would be refused and only a departure fixes it.
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ status: "inactive" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    await openMenu();
    expect(await screen.findByRole("button", { name: /mark as left/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mark as returned/i })).toBeNull();
  });
});

describe("StudentDetail status", () => {
  it("leads with what is owed, and a button to pay the oldest month", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(
      student({ months_overdue: 1, amount_owed: "200.00", next_expected_date: "2026-12-01" }) as never,
    );
    vi.spyOn(endpoints, "getLedger").mockResolvedValue({
      ...ledger,
      entries: [
        { cycle_number: 0, expected_due_date: "2026-09-01", paid_date: "2026-09-01", days_late: 0, amount: "200.00", cumulative_drift: 0, suspended: false },
        { cycle_number: 1, expected_due_date: "2026-10-01", paid_date: "2026-10-09", days_late: 8, amount: "200.00", cumulative_drift: 8, suspended: false },
        { cycle_number: 2, expected_due_date: "2026-11-01", paid_date: null, days_late: null, amount: null, cumulative_drift: 8, suspended: false },
      ],
    } as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText(/1 month unpaid · 200 DH/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record November 2026" })).toBeInTheDocument();
    // The year as tiles: September paid, October paid late, November owed.
    expect(screen.getByRole("button", { name: /September 2026 · paid$/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /October 2026 · paid late/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /November 2026 · to pay/ })).toBeInTheDocument();
  });

  it("says plainly when the student is up to date", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText("Up to date")).toBeInTheDocument();
    expect(screen.getByText(/next payment expected on/i)).toBeInTheDocument();
  });
});

describe("StudentDetail contact buttons", () => {
  it("offers a call and a WhatsApp chat, with the number in international form", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ phone: "06 12 34 56 78" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByRole("link", { name: "Call 06 12 34 56 78" })).toHaveAttribute("href", "tel:0612345678");
    const whatsapp = screen.getByRole("link", { name: "Message 06 12 34 56 78 on WhatsApp" });
    expect(whatsapp).toHaveAttribute("href", "https://wa.me/212612345678");
    expect(whatsapp).toHaveAttribute("target", "_blank");
  });

  it("leaves WhatsApp out when the number can't be read, and shows nothing without a number", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ phone: "123" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByRole("link", { name: /^Call/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /WhatsApp/ })).toBeNull();
  });
});

describe("StudentDetail offline", () => {
  it("keeps calling possible but switches off everything that would save", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ phone: "0612345678" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    await screen.findByRole("link", { name: /^Call/ });
    act(() => reportStored("2026-11-14T09:41:00"));
    expect(screen.getByRole("button", { name: /record a payment/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /more actions/i }));
    expect(screen.getByRole("button", { name: /mark as left/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /edit details/i })).toBeDisabled();
    expect(screen.getByRole("link", { name: /^Call/ })).toBeInTheDocument(); // a phone call needs no internet
    act(() => resetConnectivity());
  });
});

describe("StudentDetail correcting a payment", () => {
  // October was paid on the 10th, 9 days late: the month a mistyped amount lives in.
  const paidLedger = {
    ...ledger,
    entries: [
      { cycle_number: 0, expected_due_date: "2026-09-01", paid_date: "2026-09-01", days_late: 0, amount: "200.00", cumulative_drift: 0, suspended: false },
      { cycle_number: 1, expected_due_date: "2026-10-01", paid_date: "2026-10-10", days_late: 9, amount: "200.00", cumulative_drift: 9, suspended: false },
    ],
  };

  async function openOctober() {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    vi.spyOn(endpoints, "getLedger").mockResolvedValue(paidLedger as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /^October 2026 · paid late/ }));
  }

  it("corrects a mistyped amount, sending only what changed", async () => {
    const update = vi.spyOn(endpoints, "updatePayment").mockResolvedValue({} as never);
    await openOctober();
    await userEvent.click(screen.getByRole("button", { name: /edit this payment/i }));
    const amount = screen.getByLabelText(/^amount/i);
    await userEvent.clear(amount);
    await userEvent.type(amount, "150");
    await userEvent.click(screen.getByRole("button", { name: /^save/i }));
    expect(update).toHaveBeenCalledWith(5, 1, { amount: "150" });
    expect(await screen.findByText(/payment corrected: october 2026/i)).toBeInTheDocument();
  });

  it("reads a French decimal comma as a decimal point", async () => {
    const update = vi.spyOn(endpoints, "updatePayment").mockResolvedValue({} as never);
    await openOctober();
    await userEvent.click(screen.getByRole("button", { name: /edit this payment/i }));
    const amount = screen.getByLabelText(/^amount/i);
    await userEvent.clear(amount);
    await userEvent.type(amount, "150,5");
    await userEvent.click(screen.getByRole("button", { name: /^save/i }));
    expect(update).toHaveBeenCalledWith(5, 1, { amount: "150.5" });
  });

  it("can't save a correction that changes nothing", async () => {
    await openOctober();
    await userEvent.click(screen.getByRole("button", { name: /edit this payment/i }));
    expect(screen.getByRole("button", { name: /^save/i })).toBeDisabled();
  });

  it("asks before deleting, and only deletes once confirmed", async () => {
    const remove = vi.spyOn(endpoints, "deletePayment").mockResolvedValue(undefined as never);
    await openOctober();
    await userEvent.click(screen.getByRole("button", { name: /delete this payment/i }));
    expect(screen.getByText(/the month will be owed again/i)).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(remove).toHaveBeenCalledWith(5, 1);
    expect(await screen.findByText(/payment deleted: october 2026/i)).toBeInTheDocument();
  });

  it("offers no correction while offline", async () => {
    await openOctober();
    act(() => reportStored("2026-11-14T09:41:00"));
    expect(screen.queryByRole("button", { name: /edit this payment/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete this payment/i })).toBeNull();
    act(() => resetConnectivity());
  });
});

describe("StudentDetail note", () => {
  it("shows the teacher's note under the status", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ note: "Paie le samedi, en espèces." }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText("Paie le samedi, en espèces.")).toBeInTheDocument();
  });

  it("adds a note in its own small sheet, not the whole edit form, then refreshes the page", async () => {
    const getStudent = vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    const listClasses = vi.spyOn(endpoints, "listClasses").mockResolvedValue([] as never);
    const update = vi.spyOn(endpoints, "updateStudent").mockResolvedValue({} as never);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /add a note/i }));
    expect(screen.queryByLabelText(/first name/i)).toBeNull();
    expect(listClasses).not.toHaveBeenCalled();
    getStudent.mockResolvedValue(student({ note: "Père : Ahmed" }) as never);
    await userEvent.type(screen.getByRole("textbox", { name: /^note$/i }), "Père : Ahmed");
    await userEvent.click(screen.getByRole("button", { name: /^save/i }));
    expect(update).toHaveBeenCalledWith(5, { note: "Père : Ahmed" });
    expect(await screen.findByText("Père : Ahmed")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(getStudent).toHaveBeenCalledTimes(2);
  });

  it("edits an existing note in the same sheet, filled in", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ note: "Paie le samedi" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /^edit$/i }));
    expect(screen.getByRole("dialog", { name: "Note on Fatima" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^note$/i })).toHaveValue("Paie le samedi");
  });

  it("can't be changed offline", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ note: "Paie le samedi" }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    await screen.findByText("Paie le samedi");
    act(() => reportStored("2026-11-14T09:41:00"));
    expect(screen.queryByRole("button", { name: /^edit$/i })).toBeNull();
    act(() => resetConnectivity());
  });
});

describe("StudentDetail punctuality", () => {
  it("puts the usual lateness and the total in one row", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(
      student({ average_days_late: 4, cumulative_drift: 34 }) as never,
    );
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText("A little late")).toBeInTheDocument();
    expect(screen.getByText("Usually 4 days late · 34 days in total")).toBeInTheDocument();
    expect(screen.queryByText("Late in total")).toBeNull();
  });

  it("says a student who pays on time does, without a 0-day average", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(
      student({ average_days_late: 0, cumulative_drift: 3 }) as never,
    );
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText("On time")).toBeInTheDocument();
    expect(screen.getByText("Pays on time · 3 days in total")).toBeInTheDocument();
  });

  it("keeps the total visible before any average exists", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ cumulative_drift: 6 }) as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText("6 days in total")).toBeInTheDocument();
    expect(screen.queryByText("On time")).toBeNull();
  });

  it("shows no group before the first payment is due, just that nothing is late", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
    renderPage();
    expect(await screen.findByText("On track")).toBeInTheDocument();
    expect(screen.queryByText("On time")).toBeNull();
  });
});

describe("StudentDetail opened on a month", () => {
  // September paid on time, October 9 days late.
  const paidLedger = {
    ...ledger,
    entries: [
      { cycle_number: 0, expected_due_date: "2026-09-01", paid_date: "2026-09-01", days_late: 0, amount: "200.00", cumulative_drift: 0, suspended: false },
      { cycle_number: 1, expected_due_date: "2026-10-01", paid_date: "2026-10-10", days_late: 9, amount: "200.00", cumulative_drift: 9, suspended: false },
    ],
  };

  beforeEach(() => {
    vi.spyOn(endpoints, "getLedger").mockResolvedValue(paidLedger as never);
    vi.spyOn(endpoints, "listPeriods").mockResolvedValue([open] as never);
  });

  it("opens that month's details, then takes the month out of the address", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    renderPage("/students/5?month=2026-10");
    const sheet = await screen.findByRole("dialog", { name: "October 2026" });
    expect(sheet).toHaveTextContent(/Lateness\s*9 days/);
    // The address is cleaned up just after the sheet opens: wait for it, a slower machine is later.
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/students\/5$/));
  });

  it("doesn't open it again once closed and the page refreshes", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    renderPage("/students/5?month=2026-10");
    await screen.findByRole("dialog", { name: "October 2026" });
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    act(() => window.dispatchEvent(new Event("online")));
    await waitFor(() => expect(endpoints.getStudent).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("turns to the school year the month is in", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ join_date: "2025-09-01" }) as never);
    vi.spyOn(endpoints, "getLedger").mockResolvedValue({
      ...paidLedger,
      entries: [
        { cycle_number: 6, expected_due_date: "2026-03-01", paid_date: "2026-03-02", days_late: 1, amount: "200.00", cumulative_drift: 1, suspended: false },
        ...paidLedger.entries,
      ],
    } as never);
    renderPage("/students/5?month=2026-03");
    expect(await screen.findByRole("dialog", { name: "March 2026" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2025–2026 school year" })).toBeInTheDocument();
  });

  it("ignores a month before the student joined, whose tile can't be opened either", async () => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student({ join_date: "2026-10-01" }) as never);
    vi.spyOn(endpoints, "getLedger").mockResolvedValue({ ...paidLedger, entries: paidLedger.entries.slice(1) } as never);
    renderPage("/students/5?month=2026-09");
    expect(await screen.findByRole("button", { name: /September 2026 · not enrolled/ })).toBeDisabled();
    // The month leaves the address in the same step that would have opened the sheet.
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/students\/5$/));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each(["2026-13", "octobre", "2020-01", "2026-07"])("ignores a month it can't show (%s)", async (month) => {
    vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
    renderPage(`/students/5?month=${month}`);
    await screen.findByText("Fatima Zahra");
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/students\/5$/));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
