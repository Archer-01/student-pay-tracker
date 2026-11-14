import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { PaymentSheetProvider } from "../components/PaymentSheet";
import { StudentDetail } from "./StudentDetail";

function student(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 5, first_name: "Fatima", last_name: "Zahra", full_name: "Fatima Zahra", phone: null,
    is_repeating: false, join_date: "2026-09-01", status: "active", class_id: null, school_class: null,
    pack_id: null, pack: null, custom_price: "200.00", price_note: null, created_at: "2026-09-01T00:00:00",
    cumulative_drift: 0, months_overdue: 0, amount_owed: "0.00", monthly_price: "200.00",
    next_expected_date: "2026-12-01", payments_count: 0, total_paid: "0.00", first_payment_date: null,
    as_of: "2026-11-14", ...over,
  };
}

const ledger = { student_id: 5, as_of: "2026-11-14", cumulative_drift: 0, entries: [] };
const open = { id: 1, student_id: 5, entry_date: "2026-09-01", leave_date: null, leave_reason: null };
const closed = { ...open, leave_date: "2026-10-15" };

async function openMenu() {
  await userEvent.click(await screen.findByRole("button", { name: /more actions/i }));
}

function renderPage() {
  renderWithProviders(
    <PaymentSheetProvider>
      <Routes>
        <Route path="/students/:id" element={<StudentDetail />} />
      </Routes>
    </PaymentSheetProvider>,
    { route: "/students/5" },
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
