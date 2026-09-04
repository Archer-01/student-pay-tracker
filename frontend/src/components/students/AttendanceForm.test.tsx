import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { AttendanceForm } from "./AttendanceForm";

const period = {
  id: 1, student_id: 1, entry_date: "2023-03-05",
  leave_date: null, leave_reason: null, created_at: "",
};

beforeEach(() => {
  vi.spyOn(endpoints, "recordLeave").mockResolvedValue(period as never);
  vi.spyOn(endpoints, "recordReturn").mockResolvedValue({
    ...period, amount_owed: "0", months_owed: 0, debt_warning: null,
  } as never);
});

describe("AttendanceForm — leaving", () => {
  it("records the departure with a reason", async () => {
    const onSuccess = vi.fn();
    renderWithProviders(
      <AttendanceForm studentId={1} mode="leave" onSuccess={onSuccess} onCancel={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText(/reason/i), "moved away");
    await userEvent.click(screen.getByRole("button", { name: /mark as left/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(vi.mocked(endpoints.recordLeave).mock.calls[0][1]).toMatchObject({
      reason: "moved away",
    });
  });

  it("says what a departure will do to the money", async () => {
    renderWithProviders(
      <AttendanceForm studentId={1} mode="leave" onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByText(/stop being owed/i)).toBeInTheDocument();
  });

  it("surfaces a refusal from the server", async () => {
    const { ApiError } = await import("../../api/client");
    vi.mocked(endpoints.recordLeave).mockRejectedValue(
      new ApiError(409, "Student 1 has already left", "period_not_open"),
    );
    renderWithProviders(
      <AttendanceForm studentId={1} mode="leave" onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /mark as left/i }));
    expect(await screen.findByText(/already left/i)).toBeInTheDocument();
  });
});

describe("AttendanceForm — returning", () => {
  it("does not ask for a reason", () => {
    renderWithProviders(
      <AttendanceForm studentId={1} mode="return" onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByLabelText(/reason/i)).not.toBeInTheDocument();
  });

  it("closes straight away when the student owes nothing", async () => {
    const onSuccess = vi.fn();
    renderWithProviders(
      <AttendanceForm studentId={1} mode="return" onSuccess={onSuccess} onCancel={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /mark as returned/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });

  it("makes the teacher acknowledge a debt, after letting the return through", async () => {
    // The return is never refused — the warning is an acknowledgement, not a gate.
    vi.mocked(endpoints.recordReturn).mockResolvedValue({
      ...period,
      amount_owed: "1200.00",
      months_owed: 4,
      debt_warning: "This student left owing 1200.00 for 4 month(s)",
    } as never);
    const onSuccess = vi.fn();
    renderWithProviders(
      <AttendanceForm studentId={1} mode="return" onSuccess={onSuccess} onCancel={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /mark as returned/i }));

    expect(await screen.findByText(/left owing money/i)).toBeInTheDocument();
    expect(screen.getByText(/1200.00/)).toBeInTheDocument();
    expect(endpoints.recordReturn).toHaveBeenCalled(); // it already happened
    expect(onSuccess).not.toHaveBeenCalled(); // but the dialog waits to be dismissed

    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onSuccess).toHaveBeenCalled();
  });
});
