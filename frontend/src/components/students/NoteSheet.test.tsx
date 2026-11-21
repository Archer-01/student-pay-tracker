import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { NoteSheet } from "./NoteSheet";

beforeEach(() => {
  vi.spyOn(endpoints, "updateStudent").mockResolvedValue({} as never);
});

function renderSheet(note: string | null, { onSaved = vi.fn(), onClose = vi.fn() } = {}) {
  renderWithProviders(<NoteSheet studentId={5} name="Fatima" note={note} onSaved={onSaved} onClose={onClose} />);
  return { onSaved, onClose, field: screen.getByRole("textbox", { name: /^note$/i }) };
}

describe("NoteSheet", () => {
  it("opens on the current note, with the reminder that it stays private", () => {
    const { field } = renderSheet("Paie le samedi");
    expect(field).toHaveValue("Paie le samedi");
    expect(screen.getByText(/never appears on the pdfs/i)).toBeInTheDocument();
  });

  it("saves the note alone, trimmed", async () => {
    const { onSaved, field } = renderSheet(null);
    await userEvent.type(field, "  Père : Ahmed  ");
    await userEvent.click(screen.getByRole("button", { name: /^save/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    // Only the note: the rest of the student is left as it is.
    expect(endpoints.updateStudent).toHaveBeenCalledWith(5, { note: "Père : Ahmed" });
  });

  it("removes the note with an explicit null when the field is emptied", async () => {
    const { onSaved, field } = renderSheet("Paie le samedi");
    await userEvent.clear(field);
    await userEvent.type(field, "   ");
    await userEvent.click(screen.getByRole("button", { name: /^save/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(endpoints.updateStudent).toHaveBeenCalledWith(5, { note: null });
  });

  it("can't save a note that hasn't changed", async () => {
    const { field } = renderSheet("Paie le samedi");
    expect(screen.getByRole("button", { name: /^save/i })).toBeDisabled();
    await userEvent.type(field, " ");
    expect(screen.getByRole("button", { name: /^save/i })).toBeDisabled();
  });

  it("cancels without saving", async () => {
    const { onClose, field } = renderSheet("Paie le samedi");
    await userEvent.type(field, " et le dimanche");
    await userEvent.click(screen.getByRole("button", { name: /^cancel/i }));
    expect(onClose).toHaveBeenCalled();
    expect(endpoints.updateStudent).not.toHaveBeenCalled();
  });

  it("shows a refusal from the server and stays open", async () => {
    const { ApiError } = await import("../../api/client");
    vi.mocked(endpoints.updateStudent).mockRejectedValue(new ApiError(404, "Student 5 not found"));
    const { onSaved, field } = renderSheet(null);
    await userEvent.type(field, "Paie le samedi");
    await userEvent.click(screen.getByRole("button", { name: /^save/i }));
    expect(await screen.findByText(/student 5 not found/i)).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
