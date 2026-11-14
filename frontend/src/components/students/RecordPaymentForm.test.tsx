import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { RecordPaymentForm } from "./RecordPaymentForm";

const today = (() => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
})();

function student(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 13, full_name: "Amina Benali", monthly_price: "250.00", months_overdue: 1,
    amount_owed: "250.00", next_expected_date: "2026-11-05", ...over,
  };
}

/** Joined in September; paid 200 for September; October is owed. */
const ledger = {
  student_id: 13, as_of: "2026-10-20", cumulative_drift: 0,
  entries: [
    { cycle_number: 0, expected_due_date: "2026-09-05", paid_date: "2026-09-05", days_late: 0, amount: "200.00", cumulative_drift: 0, suspended: false },
    { cycle_number: 1, expected_due_date: "2026-10-05", paid_date: null, days_late: null, amount: null, cumulative_drift: 0, suspended: false },
  ],
};

const onSuccess = vi.fn();

beforeEach(() => {
  onSuccess.mockReset();
  vi.spyOn(endpoints, "recordPayment").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "getStudent").mockResolvedValue(student() as never);
  vi.spyOn(endpoints, "getLedger").mockResolvedValue(ledger as never);
});

function renderForm() {
  renderWithProviders(<RecordPaymentForm studentId={13} onSuccess={onSuccess} onCancel={vi.fn()} />);
}

const amountField = () => screen.findByLabelText(/amount/i);

describe("RecordPaymentForm", () => {
  it("opens filled in: oldest unpaid month, last amount paid, today", async () => {
    renderForm();
    expect(await amountField()).toHaveValue("200"); // not the 250 price: they pay 200
    expect(screen.getByRole("radio", { name: "October 2026" })).toBeChecked();
    expect(screen.getByRole("radio", { name: /today/i })).toBeChecked();
    expect(screen.getByText(/same as last time · up to 250 DH/i)).toBeInTheDocument();
  });

  it("records in one tap in the usual case", async () => {
    renderForm();
    await userEvent.click(await screen.findByRole("button", { name: /^record 200\sDH$/i }));
    await waitFor(() =>
      expect(endpoints.recordPayment).toHaveBeenCalledWith(13, {
        paid_date: today,
        amount: "200",
        for_month: "2026-10",
      }),
    );
    expect(onSuccess).toHaveBeenCalledWith("200", "Amina Benali");
  });

  it("offers the next month in advance, after the months owed", async () => {
    renderForm();
    await amountField();
    expect(screen.getByRole("radio", { name: /November 2026.*in advance/i })).not.toBeChecked();
  });

  it("refuses more than the monthly price before sending anything", async () => {
    renderForm();
    const field = await amountField();
    await userEvent.clear(field);
    await userEvent.type(field, "300");
    await userEvent.click(screen.getByRole("button", { name: /record 300/i }));
    expect(await screen.findByText(/more than this student's monthly price/i)).toBeInTheDocument();
    expect(endpoints.recordPayment).not.toHaveBeenCalled();
  });

  it("accepts a French decimal comma and sends a decimal point", async () => {
    renderForm();
    const field = await amountField();
    await userEvent.clear(field);
    await userEvent.type(field, "199,5");
    await userEvent.click(screen.getByRole("button", { name: /record/i }));
    await waitFor(() =>
      expect(endpoints.recordPayment).toHaveBeenCalledWith(13, expect.objectContaining({ amount: "199.5" })),
    );
  });

  it("refuses a paid date in the future before the server can answer in English", async () => {
    renderForm();
    await amountField();
    await userEvent.click(screen.getByRole("radio", { name: /another date/i }));
    await userEvent.type(screen.getByLabelText(/paid date/i), "2999-01-01");
    await userEvent.click(screen.getByRole("button", { name: /record 200/i }));
    expect(await screen.findByText(/can't be in the future/i)).toBeInTheDocument();
    expect(endpoints.recordPayment).not.toHaveBeenCalled();
  });

  it("has no cap when the student has no price", async () => {
    vi.mocked(endpoints.getStudent).mockResolvedValue(student({ monthly_price: "0.00" }) as never);
    renderForm();
    const field = await amountField();
    expect(screen.queryByText(/up to/i)).toBeNull();
    await userEvent.clear(field);
    await userEvent.type(field, "450");
    await userEvent.click(screen.getByRole("button", { name: /record 450/i }));
    await waitFor(() => expect(endpoints.recordPayment).toHaveBeenCalled());
  });

  it("starts on the month it was opened for, when that month can be paid", async () => {
    renderWithProviders(
      <RecordPaymentForm studentId={13} initialMonth="2026-11" onSuccess={onSuccess} onCancel={vi.fn()} />,
    );
    await amountField();
    expect(screen.getByRole("radio", { name: /November 2026/i })).toBeChecked();
  });
});
