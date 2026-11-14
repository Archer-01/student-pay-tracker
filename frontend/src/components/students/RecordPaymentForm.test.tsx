import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { RecordPaymentForm } from "./RecordPaymentForm";

beforeEach(() => {
  vi.spyOn(endpoints, "recordPayment").mockResolvedValue({} as never);
});

async function fill(amount: string) {
  await userEvent.type(screen.getByLabelText(/for month/i), "2026-10");
  await userEvent.type(screen.getByLabelText(/paid date/i), "2026-10-10");
  await userEvent.type(screen.getByLabelText(/amount/i), amount);
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
}

function renderForm(monthlyPrice: string) {
  renderWithProviders(
    <RecordPaymentForm
      studentId={13}
      monthlyPrice={monthlyPrice}
      onSuccess={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
}

describe("RecordPaymentForm", () => {
  it("shows the student's monthly price beside the amount", () => {
    renderForm("200.00");
    expect(screen.getByText(/up to 200\.00/i)).toBeInTheDocument();
  });

  it("refuses more than the monthly price before sending anything", async () => {
    // The slip this exists for: 250 typed for a student whose agreed price is 200.
    renderForm("200.00");
    await fill("250");
    expect(await screen.findByText(/more than this student's monthly price/i)).toBeInTheDocument();
    expect(endpoints.recordPayment).not.toHaveBeenCalled();
  });

  it("accepts the price itself, or less", async () => {
    renderForm("200.00");
    await fill("200");
    await waitFor(() => expect(endpoints.recordPayment).toHaveBeenCalled());
  });

  it("has no cap when the student has no price", async () => {
    renderForm("0.00");
    expect(screen.queryByText(/up to/i)).toBeNull();
    await fill("450");
    await waitFor(() => expect(endpoints.recordPayment).toHaveBeenCalled());
  });
});
