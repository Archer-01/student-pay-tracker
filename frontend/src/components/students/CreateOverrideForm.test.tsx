import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { CreateOverrideForm } from "./CreateOverrideForm";

const onSuccess = vi.fn();
const onCancel = vi.fn();

function renderForm() {
  return renderWithProviders(<CreateOverrideForm studentId={7} onSuccess={onSuccess} onCancel={onCancel} />);
}

async function fill(date: string, reason: string) {
  // Typing into a date input character by character is unreliable in jsdom; set it whole.
  fireEvent.change(screen.getByLabelText("New due date"), { target: { value: date } });
  if (reason) await userEvent.type(screen.getByLabelText("Reason"), reason);
}

const save = () => userEvent.click(screen.getByRole("button", { name: "Save" }));

beforeEach(() => {
  onSuccess.mockReset();
  onCancel.mockReset();
  vi.spyOn(endpoints, "createOverride").mockResolvedValue({} as never);
});

describe("CreateOverrideForm", () => {
  it("posts the new date and the trimmed reason for this student, then reports success", async () => {
    renderForm();
    await fill("2026-12-05", "  agreed shift  ");
    await save();

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(endpoints.createOverride).toHaveBeenCalledWith(7, {
      new_due_date: "2026-12-05",
      reason: "agreed shift",
    });
  });

  it("cannot be submitted empty", async () => {
    // Both inputs are `required`, so the browser blocks this before any handler runs.
    renderForm();
    await save();
    expect(endpoints.createOverride).not.toHaveBeenCalled();
  });

  it("asks for a reason when it is only whitespace, which `required` would accept", async () => {
    // An override is audit-logged: a change of payment day without a reason is refused.
    renderForm();
    await fill("2026-12-05", "   ");
    await save();

    expect(await screen.findByText("A reason is required.")).toBeInTheDocument();
    expect(endpoints.createOverride).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("names every missing field when the browser's own check is bypassed", async () => {
    // A submit event skips constraint validation, which is the only way to reach the date
    // message: with `required` on the input, a click never gets this far without one.
    const { container } = renderForm();
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByText("New due date is required.")).toBeInTheDocument();
    expect(screen.getByText("A reason is required.")).toBeInTheDocument();
    expect(endpoints.createOverride).not.toHaveBeenCalled();
  });

  it("shows a validation error from the server under its field", async () => {
    vi.mocked(endpoints.createOverride).mockRejectedValue(
      new ApiError(422, [{ loc: ["body", "reason"], msg: "String should have at least 1 character", type: "string_too_short" }]),
    );
    renderForm();
    await fill("2026-12-05", "agreed shift");
    await save();

    expect(await screen.findByText("String should have at least 1 character")).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows a validation error about the whole form above the buttons, not nowhere", async () => {
    vi.mocked(endpoints.createOverride).mockRejectedValue(
      new ApiError(422, [{ loc: ["body"], msg: "Value error, dates out of order", type: "value_error" }]),
    );
    renderForm();
    await fill("2026-12-05", "agreed shift");
    await save();

    expect(await screen.findByText(/dates out of order/)).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows the server's explanation when it refuses the date", async () => {
    // 400 when the date is on or before the join date, or earlier than an existing override.
    vi.mocked(endpoints.createOverride).mockRejectedValue(
      new ApiError(400, "The new date must be after the join date.", "invalid_override"),
    );
    renderForm();
    await fill("2020-01-01", "agreed shift");
    await save();

    expect(await screen.findByText("The new date must be after the join date.")).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("falls back to a generic message for anything that isn't an API error", async () => {
    vi.mocked(endpoints.createOverride).mockRejectedValue(new Error("boom"));
    renderForm();
    await fill("2026-12-05", "agreed shift");
    await save();

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("clears the previous error when submitting again", async () => {
    vi.mocked(endpoints.createOverride).mockRejectedValueOnce(new ApiError(400, "Refused."));
    renderForm();
    await fill("2026-12-05", "agreed shift");
    await save();
    expect(await screen.findByText("Refused.")).toBeInTheDocument();

    await save();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Refused.")).not.toBeInTheDocument();
  });

  it("disables Save while the request is in flight, so one tap makes one override", async () => {
    let resolve!: (value: never) => void;
    vi.mocked(endpoints.createOverride).mockReturnValue(new Promise((r) => (resolve = r)));
    renderForm();
    await fill("2026-12-05", "agreed shift");
    await save();

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    resolve({} as never);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it("cancels without saving anything", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(endpoints.createOverride).not.toHaveBeenCalled();
  });
});
