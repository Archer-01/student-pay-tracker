import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { PaymentSheetProvider } from "../components/PaymentSheet";
import { Dashboard } from "./Dashboard";

function digest(over: Partial<Record<string, unknown>> = {}) {
  return {
    student_id: 1, name: "Amina Benali", class_label: "2BAC — Groupe A",
    monthly_price: "300.00", cumulative_drift: 25, months_overdue: 2,
    amount_owed: "600.00", ...over,
  };
}

function summary(over: Partial<Record<string, unknown>> = {}) {
  return {
    as_of: "2026-11-14",
    total_collected_this_month: "1300.00",
    share_this_month: { percent: "25", school: "325.00", teacher: "975.00" },
    total_outstanding: "6400.00",
    active_students: 4,
    leavers_with_debt: 0,
    owed_by_leavers: "0",
    top_debtors: [],
    unbilled_students: [],
    missing_leave_date: [],
    ...over,
  };
}

function renderHome() {
  renderWithProviders(
    <PaymentSheetProvider>
      <Dashboard />
    </PaymentSheetProvider>,
  );
}

const chaseList = () => within(screen.getByRole("list", { name: /who to chase/i }));

beforeEach(() => {
  vi.spyOn(endpoints, "getDashboardSummary");
});

describe("Accueil", () => {
  it("names the month and shows what came in and what is owed, in dirhams", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    expect(await screen.findByRole("heading", { level: 1, name: "November 2026" })).toBeInTheDocument();
    expect(screen.getByText("1,300 DH")).toBeInTheDocument();
    expect(screen.getByText("6,400 DH")).toBeInTheDocument();
  });

  it("puts taking a payment one tap away", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    vi.spyOn(endpoints, "listStudents").mockResolvedValue([]);
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: /record a payment/i }));
    // No student given, so the sheet starts by asking who.
    expect(await screen.findByRole("dialog", { name: /record a payment/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search for a student/i)).toBeInTheDocument();
  });

  it("ranks who to chase by money, one line each, keeping lateness visible", async () => {
    // The biggest debtor may have almost no lateness; both facts stay on the row.
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({
        top_debtors: [
          digest({ student_id: 2, name: "Youssef El Amrani", amount_owed: "900.00", months_overdue: 3, cumulative_drift: 1 }),
          digest({ student_id: 1, name: "Amina Benali", amount_owed: "240.00", months_overdue: 1, cumulative_drift: 25 }),
        ],
      }) as never,
    );
    renderHome();
    await screen.findByText("Youssef El Amrani");
    const rows = chaseList().getAllByRole("link");
    expect(rows[0]).toHaveTextContent("Youssef El Amrani");
    expect(rows[0]).toHaveTextContent("900 DH");
    expect(rows[0]).toHaveTextContent("3 months unpaid");
    expect(rows[0]).toHaveTextContent("1 day late");
    expect(rows[0]).toHaveAttribute("href", "/students/2");
    expect(rows[1]).toHaveTextContent("240 DH");
    expect(rows[1]).toHaveTextContent("1 month unpaid");
    expect(rows[1]).toHaveTextContent("25 days late");
  });

  it("says so plainly when nobody owes anything", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    expect(await screen.findByText(/everyone is up to date/i)).toBeInTheDocument();
  });

  it("stays quiet when there is nothing needing attention, and no leavers owe", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    await screen.findByText("1,300 DH");
    expect(screen.queryByText(/needs attention/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/left owing/i)).not.toBeInTheDocument();
  });

  it("flags a student with no price, with a way to fix it", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ unbilled_students: [digest({ student_id: 6, name: "Mehdi Alaoui", amount_owed: "0" })] }) as never,
    );
    renderHome();
    expect(await screen.findByText(/needs attention/i)).toBeInTheDocument();
    expect(screen.getByText(/Mehdi Alaoui has no price/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /choose a pack/i })).toHaveAttribute("href", "/students/6");
  });

  it("flags someone marked as gone whose billing is still running", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ missing_leave_date: [digest({ student_id: 5, name: "Fatima Zahra" })] }) as never,
    );
    renderHome();
    expect(await screen.findByText(/no departure date/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /fix/i })).toHaveAttribute("href", "/students/5");
  });

  it("links to former students who left owing, when there are some", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ leavers_with_debt: 2, owed_by_leavers: "6170.00" }) as never,
    );
    renderHome();
    const link = await screen.findByRole("link", { name: /left owing/i });
    expect(link).toHaveAttribute("href", "/reports/leavers");
    expect(link).toHaveTextContent("6,170 DH");
    expect(link).toHaveTextContent("2");
  });

  it("surfaces a failed load instead of an empty page", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockRejectedValue(new Error("down"));
    renderHome();
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("says how much of this month's money is yours, after the school's share", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    expect(await screen.findByText("of which 975 DH is yours")).toBeInTheDocument();
  });

  it("says nothing about a share when there is none", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ share_this_month: { percent: "0", school: "0.00", teacher: "1300.00" } }) as never,
    );
    renderHome();
    await screen.findByText("1,300 DH");
    expect(screen.queryByText(/is yours/)).toBeNull();
  });
});
