import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { StudentsList } from "./StudentsList";

function student(over: Partial<Record<string, unknown>>) {
  return {
    id: 1, full_name: "Amina Benali", is_repeating: false, status: "active",
    school_class: { id: 5, level: "2BAC", name: "Groupe A" }, cumulative_drift: 0,
    months_overdue: 0, amount_owed: "0.00", monthly_price: "240.00", average_days_late: 0, ...over,
  };
}

const rows = [
  student({ id: 3, full_name: "Youssef El Amrani", months_overdue: 2, amount_owed: "600.00", cumulative_drift: 9, average_days_late: 9 }),
  student({ id: 1, full_name: "Amina Benali" }),
  student({ id: 2, full_name: "Karim Bennis", months_overdue: 1, amount_owed: "190.00", school_class: null, average_days_late: 4 }),
  student({ id: 4, full_name: "Zineb Nouri", average_days_late: null }),
];

beforeEach(() => {
  vi.spyOn(endpoints, "listStudents").mockResolvedValue(rows as never);
  vi.spyOn(endpoints, "listClasses").mockResolvedValue([{ id: 5, level: "2BAC", name: "Groupe A" }] as never);
});

const list = () => within(screen.getByRole("list", { name: "Students" }));

describe("StudentsList", () => {
  it("lists current students alphabetically, one line each", async () => {
    renderWithProviders(<StudentsList />);
    await screen.findByText("Amina Benali");
    const names = list().getAllByRole("link").map((a) => a.textContent);
    expect(names[0]).toMatch(/^AB.*Amina Benali/);
    expect(names[1]).toMatch(/Karim Bennis/);
    expect(names[2]).toMatch(/Youssef El Amrani/);
    expect(endpoints.listStudents).toHaveBeenCalledWith(expect.objectContaining({ status: "active" }));
  });

  it("says on each row what is owed, how many months and how late", async () => {
    renderWithProviders(<StudentsList />);
    const row = (await screen.findByText("Youssef El Amrani")).closest("a")!;
    expect(row).toHaveTextContent("600 DH");
    expect(row).toHaveTextContent("2 months unpaid");
    expect(row).toHaveTextContent("9 days late");
    expect(row).toHaveTextContent("2BAC Groupe A");
    expect(row).toHaveAttribute("href", "/students/3");
  });

  it("shows who owes money, most first, with one tap", async () => {
    renderWithProviders(<StudentsList />);
    await screen.findByText("Amina Benali");
    await userEvent.click(screen.getByRole("radio", { name: "Unpaid" }));
    await waitFor(() => expect(list().getAllByRole("link")).toHaveLength(2));
    const names = list().getAllByRole("link").map((a) => a.textContent);
    expect(names[0]).toMatch(/Youssef/);
    expect(names[1]).toMatch(/Karim/);
  });

  it("filters by class from a chip, and keeps former students behind their own chip", async () => {
    renderWithProviders(<StudentsList />);
    await screen.findByText("Amina Benali");
    await userEvent.click(screen.getByRole("radio", { name: "2BAC Groupe A" }));
    await waitFor(() =>
      expect(endpoints.listStudents).toHaveBeenLastCalledWith(expect.objectContaining({ class_id: 5, status: "active" })),
    );
    await userEvent.click(screen.getByRole("radio", { name: "Former" }));
    await waitFor(() =>
      expect(endpoints.listStudents).toHaveBeenLastCalledWith(expect.objectContaining({ status: "inactive" })),
    );
  });

  it("ranks who pays late, worst first, leaving out students with nothing due yet", async () => {
    renderWithProviders(<StudentsList />);
    await screen.findByText("Amina Benali");
    await userEvent.click(screen.getByRole("radio", { name: "Punctuality" }));
    const shown = list().getAllByRole("link").map((a) => a.textContent);
    expect(shown).toEqual([
      expect.stringMatching(/Youssef El Amrani.*Usually 9 days late.*Often late/),
      expect.stringMatching(/Karim Bennis.*Usually 4 days late.*A little late/),
      expect.stringMatching(/Amina Benali.*Pays on time.*On time/),
    ]);
  });
});
