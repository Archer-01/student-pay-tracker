import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
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
    const popup = vi.spyOn(window, "confirm");
    renderWithProviders(
      <EditStudentForm studentId={1} initial={initial} onSuccess={vi.fn()} onCancel={vi.fn()} />,
    );
    const price = screen.getByLabelText(/agreed price/i);
    await userEvent.clear(price);
    await userEvent.type(price, "0");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText(/0 DH.*never be chased/)).toBeInTheDocument();
    // While it asks, the form's own buttons give way to the question's.
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "No, go back" }));
    expect(endpoints.updateStudent).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await confirmAndSave()).toMatchObject({ custom_price: "0" });
    expect(popup).not.toHaveBeenCalled();
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
