import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { Dashboard } from "./Dashboard";

function digest(over: Partial<Record<string, unknown>> = {}) {
  return {
    student_id: 1, name: "Amina Benali", class_label: "2BAC — Groupe A",
    monthly_price: "300.00", cumulative_drift: 25, months_overdue: 13,
    amount_owed: "3900.00", ...over,
  };
}

function summary(over: Partial<Record<string, unknown>> = {}) {
  return {
    as_of: "2024-06-30",
    total_collected_this_month: "1300.00",
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

beforeEach(() => {
  vi.spyOn(endpoints, "getDashboardSummary");
});

describe("Dashboard", () => {
  it("shows what came in and what is owed", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("1,300.00")).toBeInTheDocument();
    expect(screen.getByText("6,400.00")).toBeInTheDocument();
  });

  it("hides the leavers tile when nobody left owing", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderWithProviders(<Dashboard />);
    await screen.findByText("1,300.00");
    expect(screen.queryByText(/left owing/i)).not.toBeInTheDocument();
  });

  it("shows the leavers tile when there is money to chase", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ leavers_with_debt: 2, owed_by_leavers: "6170.00" }) as never,
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText("6,170.00")).toBeInTheDocument();
    expect(screen.getByText("(2)")).toBeInTheDocument();
  });

  it("ranks the chase list by money, keeping drift visible", async () => {
    // The point of the rework: the biggest debtor may have almost no drift.
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({
        top_debtors: [
          digest({ student_id: 2, name: "Youssef", amount_owed: "9900.00", cumulative_drift: 1 }),
          digest({ student_id: 1, name: "Amina", amount_owed: "9360.00", cumulative_drift: 25 }),
        ],
      }) as never,
    );
    renderWithProviders(<Dashboard />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Youssef");
    expect(rows[0]).toHaveTextContent("9,900.00");
    expect(rows[1]).toHaveTextContent("Amina");
  });

  it("says so plainly when nobody owes anything", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/nobody owes anything/i)).toBeInTheDocument();
  });

  it("stays quiet when there is nothing needing attention", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderWithProviders(<Dashboard />);
    await screen.findByText("1,300.00");
    expect(screen.queryByText(/needs attention/i)).not.toBeInTheDocument();
  });

  it("flags a student who has no pack and is therefore charged nothing", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({
        unbilled_students: [digest({ student_id: 6, name: "Mehdi Alaoui", amount_owed: "0" })],
      }) as never,
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/needs attention/i)).toBeInTheDocument();
    expect(screen.getByText(/no pack and is being charged nothing/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mehdi Alaoui" })).toHaveAttribute(
      "href",
      "/students/6",
    );
  });

  it("flags someone marked as gone whose billing is still running", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ missing_leave_date: [digest({ student_id: 5, name: "Fatima Zahra" })] }) as never,
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/no departure date/i)).toBeInTheDocument();
  });

  it("surfaces a failed load instead of an empty page", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockRejectedValue(new Error("down"));
    renderWithProviders(<Dashboard />);
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });
});
