import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { ApiError } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { EditStudentForm } from "./EditStudentForm";

const initial = {
  firstName: "Amina",
  lastName: "Benali",
  isRepeating: false,
  phone: "+212600112233",
  classId: null,
  packId: null,
  customPrice: "90",
  priceNote: "remise fratrie",
  note: "Paie le samedi",
  joinDate: "2026-09-05",
  paymentsCount: 0,
};

beforeEach(() => {
  vi.spyOn(endpoints, "listPacks").mockResolvedValue([]);
  vi.spyOn(endpoints, "listClasses").mockResolvedValue([]);
  vi.spyOn(endpoints, "updateStudent").mockResolvedValue({} as never);
});

/** Answers the sheet's question, then waits for the save. */
async function confirmAndSave() {
  await userEvent.click(screen.getByRole("button", { name: "Yes, save" }));
  await waitFor(() => expect(endpoints.updateStudent).toHaveBeenCalled());
  return vi.mocked(endpoints.updateStudent).mock.calls[0][1];
}

async function save() {
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(endpoints.updateStudent).toHaveBeenCalled());
  return vi.mocked(endpoints.updateStudent).mock.calls[0][1];
}

describe("EditStudentForm", () => {
  it("sends explicit nulls to clear a field, not an omitted key", async () => {
    // The backend treats an omitted key as "leave unchanged", so clearing the agreed price or
    // the class has to travel as null. Getting this wrong makes clearing silently do nothing.
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    await userEvent.clear(screen.getByLabelText(/agreed price/i));
    const body = await save();
    expect(body).toMatchObject({ custom_price: null, class_id: null, pack_id: null });
    expect("custom_price" in body).toBe(true);
  });

  it("keeps the agreed price when it was not touched", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(await save()).toMatchObject({ custom_price: "90", price_note: "remise fratrie" });
  });

  it("sends money as a string, never a number", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(typeof (await save()).custom_price).toBe("string");
  });

  it("clears a blank surname to null rather than an empty string", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    await userEvent.clear(screen.getByLabelText(/last name/i));
    expect(await save()).toMatchObject({ last_name: null });
  });

  it("cannot be submitted with an empty first name", async () => {
    // The field is `required`, so the browser blocks this one before any handler runs — which is
    // why the test asserts on the request not happening rather than on our own message.
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    await userEvent.clear(screen.getByLabelText(/first name/i));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
  });

  it("explains itself when the first name is only whitespace", async () => {
    // `required` is satisfied by a space, so this is the case our own validation exists for.
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const firstName = screen.getByLabelText(/first name/i);
    await userEvent.clear(firstName);
    await userEvent.type(firstName, "   ");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/first name is required/i)).toBeInTheDocument();
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
  });

  it("rejects a negative agreed price before it reaches the server", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const price = screen.getByLabelText(/agreed price/i);
    await userEvent.clear(price);
    await userEvent.type(price, "-5");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
  });

  it("only asks why when there is an agreed price to explain", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByLabelText(/why/i)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/agreed price/i));
    await waitFor(() => expect(screen.queryByLabelText(/why/i)).not.toBeInTheDocument());
  });

  it("never sends a status: departures go through 'Mark as left', which records the date", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByLabelText(/status/i)).toBeNull();
    const body = await save();
    expect(body).not.toHaveProperty("status");
  });

  it("sends the note trimmed, and null once emptied", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const note = screen.getByLabelText(/^note/i);
    await userEvent.clear(note);
    await userEvent.type(note, "  Père : Ahmed  ");
    expect(await save()).toMatchObject({ note: "Père : Ahmed" });
  });

  it("clears an emptied note with an explicit null", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    await userEvent.clear(screen.getByLabelText(/^note/i));
    const body = await save();
    expect("note" in body && body.note === null).toBe(true);
  });
});

describe("EditStudentForm, a price of 0", () => {
  it("asks before making a student free, and saves nothing if the answer is no", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const price = screen.getByLabelText(/agreed price/i);
    await userEvent.clear(price);
    await userEvent.type(price, "0");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(screen.getByText(/0 DH.*never be chased/)).toBeInTheDocument();
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
    expect(await confirmAndSave()).toMatchObject({ custom_price: "0" });
  });

  it("doesn't ask again when the student was already free", async () => {
    renderWithProviders(
      <EditStudentForm
        studentId={1}
        initial={{ ...initial, customPrice: "0.00" }}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await save();
    expect(screen.queryByRole("button", { name: "Yes, save" })).not.toBeInTheDocument();
  });
});

describe("EditStudentForm, the join date (decision 0015)", () => {
  it("leaves the join date out when it wasn't changed", async () => {
    // A student with payments would otherwise be refused on every save.
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    expect("join_date" in (await save())).toBe(false);
  });

  it("asks in the sheet before correcting the join date, and sends it once confirmed", async () => {
    // A slip in the date picker while fixing a phone number would recompute every month.
    const popup = vi.spyOn(window, "confirm");
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Join date"), { target: { value: "2026-10-12" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(screen.getByText(/worked out again from Oct 12, 2026/)).toBeInTheDocument();
    // While it asks, the form's own buttons give way to the question's.
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "No, go back" }));
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await confirmAndSave()).toMatchObject({ join_date: "2026-10-12" });
    expect(popup).not.toHaveBeenCalled();
  });

  it("asks both questions at once when the date and a price of 0 change together", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Join date"), { target: { value: "2026-10-12" } });
    const price = screen.getByLabelText(/agreed price/i);
    await userEvent.clear(price);
    await userEvent.type(price, "0");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(screen.getByText(/never be chased/)).toBeInTheDocument();
    expect(screen.getByText(/will be worked out again/)).toBeInTheDocument();
    expect(await confirmAndSave()).toMatchObject({ join_date: "2026-10-12", custom_price: "0" });
  });

  it("locks the date and says why once payments are recorded", () => {
    renderWithProviders(
      <EditStudentForm
        studentId={1}
        initial={{ ...initial, paymentsCount: 2 }}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Join date")).toBeDisabled();
    expect(screen.getByText("2 payments are recorded: delete them first to correct this date.")).toBeInTheDocument();
  });

  it("won't send an emptied date", async () => {
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Join date"), { target: { value: "" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("The join date is required.")).toBeInTheDocument();
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
  });

  it("when the server refuses the date, says why under it, puts it back and locks it", async () => {
    vi.mocked(endpoints.updateStudent).mockRejectedValueOnce(
      new ApiError(409, "This student's debt was written off.", "join_date_has_writeoffs"),
    );
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const field = screen.getByLabelText("Join date");
    fireEvent.change(field, { target: { value: "2026-10-12" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, save" }));
    expect(await screen.findByText("This student's debt was written off.")).toBeInTheDocument();
    expect(field).toHaveValue("2026-09-05");
    expect(field).toBeDisabled();
    // So the next save, of anything else, goes through without the date.
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(endpoints.updateStudent).toHaveBeenCalledTimes(2));
    expect("join_date" in vi.mocked(endpoints.updateStudent).mock.calls[1][1]).toBe(false);
  });

  it("a date after the changed payment day is said under the field, which stays open", async () => {
    // Another date before it is fine, so the field must not lock.
    vi.mocked(endpoints.updateStudent).mockRejectedValueOnce(
      new ApiError(409, "The join date must come before it.", "join_date_after_payment_day"),
    );
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const field = screen.getByLabelText("Join date");
    fireEvent.change(field, { target: { value: "2026-10-25" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, save" }));
    expect(await screen.findByText("The join date must come before it.")).toBeInTheDocument();
    expect(field).toHaveValue("2026-10-25");
    expect(field).not.toBeDisabled();
  });

  it("keeps the server's reason as the hint once it locked the date", async () => {
    // Not « Un paiement est enregistré » for a student with no payments, on a later failed save.
    vi.mocked(endpoints.updateStudent)
      .mockRejectedValueOnce(new ApiError(409, "This student's debt was written off.", "join_date_has_writeoffs"))
      .mockRejectedValueOnce(new ApiError(500, "Server unavailable"));
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Join date"), { target: { value: "2026-10-12" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, save" }));
    await screen.findByText("This student's debt was written off.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(endpoints.updateStudent).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("This student's debt was written off.")).toBeInTheDocument();
    expect(screen.queryByText(/payments? (is|are) recorded/)).not.toBeInTheDocument();
  });

  it("locks the date when the server finds payments the sheet didn't know about", async () => {
    vi.mocked(endpoints.updateStudent).mockRejectedValueOnce(
      new ApiError(409, "A payment is recorded for this student.", "join_date_has_payments"),
    );
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const field = screen.getByLabelText("Join date");
    fireEvent.change(field, { target: { value: "2026-10-12" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, save" }));
    expect(await screen.findByText("A payment is recorded for this student.")).toBeInTheDocument();
    expect(field).toBeDisabled();
    expect(field).toHaveValue("2026-09-05");
  });

  it("a date after the student left is said under the field, which stays open", async () => {
    vi.mocked(endpoints.updateStudent).mockRejectedValueOnce(
      new ApiError(409, "The join date can't be after they left.", "join_date_after_leave"),
    );
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const field = screen.getByLabelText("Join date");
    fireEvent.change(field, { target: { value: "2026-12-01" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, save" }));
    expect(await screen.findByText("The join date can't be after they left.")).toBeInTheDocument();
    expect(field).not.toBeDisabled();
  });
});
