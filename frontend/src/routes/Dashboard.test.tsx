import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { act, screen, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { PaymentSheetProvider } from "../components/PaymentSheet";
import { Dashboard } from "./Dashboard";
import { reportStored, resetConnectivity } from "../lib/connectivity";

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
    this_month: { expected: "0", settled: "0", students_expected: 0, students_settled: 0 },
    due_this_week: [],
    school_share_pending: null,
    recorded_today: [],
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
    // Short enough not to wrap on a phone: no date, the home page is always today.
    expect(screen.getByText("Owed today")).toBeInTheDocument();
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

  it("ranks who to chase by money, one short line each: months unpaid and class", async () => {
    // Lateness is left to Ponctualité: on a phone it pushed the class off the end of the line.
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
    expect(rows[0]).toHaveTextContent("3 months unpaid · 2BAC — Groupe A");
    expect(rows[0]).toHaveAttribute("href", "/students/2");
    expect(rows[1]).toHaveTextContent("240 DH");
    expect(rows[1]).toHaveTextContent("1 month unpaid · 2BAC — Groupe A");
    expect(chaseList().queryByText(/late/)).toBeNull();
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

  it("switches off taking a payment while showing stored data offline", async () => {
    // Read only: a payment can't be saved without a connection, so the button says so up front
    // rather than letting the teacher fill in a sheet that fails at the end.
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    await screen.findByText("1,300 DH");
    act(() => reportStored("2026-11-14T09:41:00"));
    expect(screen.getByRole("button", { name: /record a payment/i })).toBeDisabled();
    act(() => resetConnectivity());
    expect(screen.getByRole("button", { name: /record a payment/i })).toBeEnabled();
  });
});

describe("Accueil, this month's fees and the week ahead", () => {
  it("shows how far along this month's fees are", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({
        this_month: { expected: "3200.00", settled: "2450.00", students_expected: 12, students_settled: 9 },
      }) as never,
    );
    renderHome();
    expect(await screen.findByText(/9 of 12 students paid/i)).toBeInTheDocument();
    expect(screen.getByText(/2,450 DH of 3,200 DH/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /this month's fees/i })).toHaveAttribute("aria-valuenow", "77");
  });

  it("leaves the fees out when nothing is due this month", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    await screen.findByText(/collected this month/i);
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("lists who is due this week, saying today and tomorrow in words", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({
        due_this_week: [
          { student_id: 4, name: "Omar Tazi", class_label: "TC — Groupe A", due_date: "2026-11-14", amount: "200.00" },
          { student_id: 7, name: "Sara Idrissi", class_label: null, due_date: "2026-11-15", amount: "220.00" },
          { student_id: 9, name: "Ilyas Tahiri", class_label: null, due_date: "2026-11-18", amount: "150.00" },
        ],
      }) as never,
    );
    renderHome();
    const week = within(await screen.findByRole("list", { name: /this week/i }));
    const rows = week.getAllByRole("link");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringMatching(/Omar Tazi.*Due today.*200\sDH/),
      expect.stringMatching(/Sara Idrissi.*Due tomorrow.*220\sDH/),
      expect.stringMatching(/Ilyas Tahiri.*Due Wednesday.*150\sDH/),
    ]);
  });

  it("leaves the week out when nobody is due", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    await screen.findByText(/collected this month/i);
    expect(screen.queryByRole("list", { name: /this week/i })).toBeNull();
  });
});

describe("Accueil, the school's share", () => {
  it("reminds that last month's share is still to hand over, with a link to do it", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({ school_share_pending: { year: 2026, month: 10, remaining: "402.50" } }) as never,
    );
    renderHome();
    expect(await screen.findByText(/school's share to hand over \(October 2026\)/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /hand over/i })).toHaveAttribute("href", "/reports/school");
  });
});

describe("Accueil, what was recorded today", () => {
  const recorded = (over: Partial<Record<string, unknown>> = {}) => ({
    student_id: 3, name: "Omar Tazi", class_label: "TC — Groupe A", cycle_number: 2,
    for_month: "2026-11", paid_date: "2026-11-14", amount: "200.00", ...over,
  });

  it("lists today's payments right under the pay button, each opening its month", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(
      summary({
        recorded_today: [
          recorded(),
          // Back-dated: September's, paid on 5 September, typed in today.
          recorded({ student_id: 8, name: "Sara Idrissi", for_month: "2026-09", paid_date: "2026-09-05", amount: "240.00" }),
        ],
      }) as never,
    );
    renderHome();
    const heading = await screen.findByRole("heading", { name: "Collected today · 2" });
    const rows = within(screen.getByRole("list", { name: "Collected today" })).getAllByRole("link");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringMatching(/Omar Tazi.*November 2026.*200\sDH/),
      expect.stringMatching(/Sara Idrissi.*September 2026 · paid on Sep 5.*240\sDH/),
    ]);
    // Paid today goes without saying.
    expect(rows[0]).not.toHaveTextContent(/paid on/);
    expect(rows[0]).toHaveAttribute("href", "/students/3?month=2026-11");
    expect(rows[1]).toHaveAttribute("href", "/students/8?month=2026-09");
    expect(screen.getByText("Tap a line to fix a typo.")).toBeInTheDocument();
    // Straight after the pay button, before anything needing attention or the chase list.
    expect(screen.getByRole("button", { name: /record a payment/i }).nextElementSibling).toContainElement(heading);
  });

  it("leaves the section out when nothing was recorded today", async () => {
    vi.mocked(endpoints.getDashboardSummary).mockResolvedValue(summary() as never);
    renderHome();
    await screen.findByText(/collected this month/i);
    expect(screen.queryByText(/collected today/i)).toBeNull();
    expect(screen.queryByText(/fix a typo/i)).toBeNull();
  });
});
