import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { EnrollStudent } from "./EnrollStudent";

const pack = (id: number, name: string, level: string) => ({
  id, name, level, price: "240.00", is_active: true, created_at: "", subjects: ["Maths"], student_count: 0,
});

const classes = [
  { id: 5, level: "2BAC", name: "Groupe A" },
  { id: 6, level: "1AC", name: "Groupe B" },
  { id: 7, level: "TC", name: "Groupe C" },
];

beforeEach(() => {
  vi.spyOn(endpoints, "listClasses").mockResolvedValue(classes as never);
  vi.spyOn(endpoints, "listPacks").mockResolvedValue([
    pack(1, "Pack 2BAC", "2BAC"),
    pack(2, "Pack 1AC Maths", "1AC"),
    pack(3, "Pack 1AC complet", "1AC"),
  ] as never);
  vi.spyOn(endpoints, "findSimilarLeavers").mockResolvedValue([] as never);
});

const classField = () => screen.getByLabelText("Class") as HTMLSelectElement;
const packField = () => screen.getByLabelText("Pack") as HTMLSelectElement;

async function chooseClass(id: string) {
  await waitFor(() => expect(classField().querySelectorAll("option")).toHaveLength(4));
  await waitFor(() => expect(packField().querySelectorAll("option")).toHaveLength(4));
  await userEvent.selectOptions(classField(), id);
}

describe("EnrollStudent, the pack", () => {
  it("picks the class's only pack, says so, and enrols the student on it", async () => {
    const create = vi.spyOn(endpoints, "createStudent").mockResolvedValue({ id: 42 } as never);
    renderWithProviders(<EnrollStudent />);
    await chooseClass("5");
    expect(packField()).toHaveValue("1");
    expect(screen.getByText("Picked from the class")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/first name/i), "Amina");
    await userEvent.click(screen.getByRole("button", { name: "Enroll student" }));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ class_id: 5, pack_id: 1 }));
  });

  it("leaves the pack to the teacher when the level has several", async () => {
    renderWithProviders(<EnrollStudent />);
    await chooseClass("6");
    expect(packField()).toHaveValue("");
    expect(screen.queryByText("Picked from the class")).not.toBeInTheDocument();
  });

  it("follows the class while the pack is still its own pick, and lets go with no match", async () => {
    renderWithProviders(<EnrollStudent />);
    await chooseClass("5");
    expect(packField()).toHaveValue("1");
    await userEvent.selectOptions(classField(), "7");
    expect(packField()).toHaveValue("");
    expect(screen.queryByText("Picked from the class")).not.toBeInTheDocument();
  });

  it("never replaces a pack the teacher chose", async () => {
    renderWithProviders(<EnrollStudent />);
    await chooseClass("6");
    await userEvent.selectOptions(packField(), "2");
    await userEvent.selectOptions(classField(), "5");
    expect(packField()).toHaveValue("2");
    expect(screen.queryByText("Picked from the class")).not.toBeInTheDocument();
  });

  it("picks the pack for a class preset from the class page", async () => {
    renderWithProviders(<EnrollStudent />, { route: "/students/new?class_id=5" });
    await waitFor(() => expect(packField()).toHaveValue("1"));
    expect(screen.getByText("Picked from the class")).toBeInTheDocument();
  });
});
