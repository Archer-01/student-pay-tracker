import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { PacksList } from "./PacksList";

function pack(over: Partial<Record<string, unknown>>) {
  return {
    id: 1, name: "Pack", level: "TC", price: "400.00", is_active: true, created_at: "2026-09-01T00:00:00",
    subjects: ["Maths", "Physique"], student_count: 0, ...over,
  };
}

const packs = [
  pack({ id: 3, name: "Pack TC Scientifique", level: "TC", price: "400.00", student_count: 7 }),
  pack({ id: 1, name: "Enaja7", level: "3AC", price: "500.00", subjects: ["Anglais", "Maths"], student_count: 39 }),
  pack({ id: 9, name: "Ancien pack", level: "1BAC", price: "300.00", is_active: false }),
];

beforeEach(() => {
  vi.spyOn(endpoints, "listPacks").mockResolvedValue(packs as never);
  vi.spyOn(endpoints, "createPack").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "updatePack").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "deletePack").mockResolvedValue(undefined as never);
});

const list = () => within(screen.getByRole("list", { name: "Packs" }));

describe("PacksList", () => {
  it("lists each pack on its own line, by school level", async () => {
    renderWithProviders(<PacksList />);
    await screen.findByText("Enaja7");
    const rows = list().getAllByRole("button");
    expect(rows[0]).toHaveTextContent("3AC");
    expect(rows[0]).toHaveTextContent("Enaja7");
    expect(rows[0]).toHaveTextContent("500 DH");
    expect(rows[0]).toHaveTextContent("39 students");
    expect(rows[1]).toHaveTextContent("Pack TC Scientifique");
    expect(rows[2]).toHaveTextContent("Ancien pack");
    expect(rows[2]).toHaveTextContent("retired");
  });

  it("creates one pack, for one level", async () => {
    renderWithProviders(<PacksList />);
    await userEvent.click(await screen.findByRole("button", { name: /new pack/i }));
    await userEvent.type(screen.getByLabelText("Pack name"), "Pack 2BAC Sciences");
    await userEvent.selectOptions(screen.getByLabelText("Level"), "2BAC");
    await userEvent.type(screen.getByLabelText("Subjects"), "Maths, Physique");
    await userEvent.type(screen.getByLabelText("Monthly price"), "450");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(endpoints.createPack).toHaveBeenCalledWith({
        name: "Pack 2BAC Sciences",
        level: "2BAC",
        subjects: ["Maths", "Physique"],
        price: "450",
      }),
    );
  });

  it("edits one pack, and locks its level once students have it", async () => {
    renderWithProviders(<PacksList />);
    await userEvent.click(await screen.findByRole("button", { name: /Pack TC Scientifique/ }));
    expect(screen.getByLabelText("Level")).toBeDisabled();
    expect(screen.getByText(/7 students are on this pack/i)).toBeInTheDocument();
    const price = screen.getByLabelText("Monthly price");
    await userEvent.clear(price);
    await userEvent.type(price, "420");
    // A price change reaches the students already on the pack, so it says so.
    expect(screen.getByText(/changes the price for 7 students/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(endpoints.updatePack).toHaveBeenCalledWith(3, {
        name: "Pack TC Scientifique",
        subjects: ["Maths", "Physique"],
        price: "420",
      }),
    );
  });

  it("can retire a pack students are on, and delete one nobody is on", async () => {
    renderWithProviders(<PacksList />);
    await userEvent.click(await screen.findByRole("button", { name: /Enaja7/ }));
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /retire this pack/i }));
    await waitFor(() => expect(endpoints.updatePack).toHaveBeenCalledWith(1, { is_active: false }));

    await userEvent.click(await screen.findByRole("button", { name: /Ancien pack/ }));
    await userEvent.click(screen.getByRole("button", { name: /delete this pack/i }));
    await waitFor(() => expect(endpoints.deletePack).toHaveBeenCalledWith(9));
  });

  it("asks for a name, at least one subject and a price", async () => {
    renderWithProviders(<PacksList />);
    await userEvent.click(await screen.findByRole("button", { name: /new pack/i }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/at least one subject/i)).toBeInTheDocument();
    expect(endpoints.createPack).not.toHaveBeenCalled();
  });
});
