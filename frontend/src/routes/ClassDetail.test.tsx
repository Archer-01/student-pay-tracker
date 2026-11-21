import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { ApiError } from "../api/client";
import { reportOffline, resetConnectivity } from "../lib/connectivity";
import { ClassDetail } from "./ClassDetail";

const schoolClass = {
  id: 5, level: "2BAC", name: "Groupe A", created_at: "2026-09-01T00:00:00", student_count: 3,
  cumulative_drift: 12, as_of: "2026-11-21",
};

function student(over: Partial<Record<string, unknown>>) {
  return {
    id: 1, full_name: "Amina Benali", status: "active", cumulative_drift: 0, months_overdue: 0,
    amount_owed: "0.00", monthly_price: "300.00", price_status: "priced", ...over,
  };
}

// Deliberately not in alphabetical order: the page sorts the roster by name.
const roster = [
  student({ id: 3, full_name: "Youssef El Amrani", months_overdue: 2, amount_owed: "600.00", cumulative_drift: 9 }),
  student({ id: 1, full_name: "Amina Benali" }),
  student({ id: 2, full_name: "Karim Bennis", status: "inactive" }),
];

beforeEach(() => {
  vi.spyOn(endpoints, "getClass").mockResolvedValue(schoolClass as never);
  vi.spyOn(endpoints, "listStudents").mockResolvedValue(roster as never);
  vi.spyOn(endpoints, "updateClass").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "deleteClass").mockResolvedValue(undefined as never);
  vi.spyOn(endpoints, "downloadClassRoster").mockResolvedValue(undefined as never);
});

afterEach(() => {
  resetConnectivity();
  vi.restoreAllMocks();
});

async function renderClass() {
  renderWithProviders(
    <Routes>
      <Route path="/settings/classes/:id" element={<ClassDetail />} />
      <Route path="/settings/classes" element={<p>All the classes</p>} />
    </Routes>,
    { route: "/settings/classes/5" },
  );
  await screen.findByRole("heading", { name: "2BAC — Groupe A" });
}

const rosterList = () => within(screen.getByRole("list", { name: "2BAC — Groupe A" }));
const dialog = () => within(screen.getByRole("dialog"));

describe("ClassDetail", () => {
  it("reads the class and its students from the id in the address", async () => {
    await renderClass();
    expect(endpoints.getClass).toHaveBeenCalledWith(5);
    expect(endpoints.listStudents).toHaveBeenCalledWith({ class_id: 5 });
    expect(screen.getByText("3 students · 12 days late")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /all classes/i })).toHaveAttribute("href", "/settings/classes");
  });

  it("leaves lateness out of the summary when nobody is late", async () => {
    vi.mocked(endpoints.getClass).mockResolvedValue({ ...schoolClass, cumulative_drift: 0 } as never);
    await renderClass();
    expect(screen.getByText("3 students")).toBeInTheDocument();
  });

  it("lists its students by name, each row linking to the student", async () => {
    await renderClass();
    const rows = rosterList().getAllByRole("link");
    expect(rows.map((r) => r.getAttribute("href"))).toEqual(["/students/1", "/students/2", "/students/3"]);
    expect(rows[0]).toHaveTextContent("Amina Benali");
    expect(rows[0]).toHaveTextContent("Up to date");
    expect(rows[1]).toHaveTextContent("Karim Bennis");
    expect(rows[1]).toHaveTextContent("Left");
    expect(rows[2]).toHaveTextContent("600 DH");
    expect(rows[2]).toHaveTextContent("2 months unpaid · 9 days late");
  });

  it("says so when the class has no students yet", async () => {
    vi.mocked(endpoints.listStudents).mockResolvedValue([] as never);
    await renderClass();
    expect(screen.getByText("No students in this class yet.")).toBeInTheDocument();
  });

  it("shows a failed load", async () => {
    vi.mocked(endpoints.getClass).mockRejectedValue(new ApiError(404, "Class not found.", "class_not_found"));
    renderWithProviders(
      <Routes>
        <Route path="/settings/classes/:id" element={<ClassDetail />} />
      </Routes>,
      { route: "/settings/classes/5" },
    );
    expect(await screen.findByText("Class not found.")).toBeInTheDocument();
  });

  it("adds a student with the class already chosen", async () => {
    await renderClass();
    expect(screen.getByRole("link", { name: "Add student" })).toHaveAttribute("href", "/students/new?class_id=5");
  });

  it("downloads the roster as a PDF named after the class, as of the class's date", async () => {
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Download roster (PDF)" }));
    expect(endpoints.downloadClassRoster).toHaveBeenCalledWith(5, "2bac-groupe-a-roster.pdf", "2026-11-21");
  });

  it("says why when the roster can't be downloaded, instead of doing nothing", async () => {
    vi.mocked(endpoints.downloadClassRoster).mockRejectedValue(new ApiError(503, "No connection.", "offline"));
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Download roster (PDF)" }));
    expect(await screen.findByText(/Not available offline yet/)).toBeInTheDocument();
  });

  it("renames the class, trimmed, then refreshes", async () => {
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const name = dialog().getByLabelText("Name");
    expect(name).toHaveValue("Groupe A");
    await userEvent.clear(name);
    await userEvent.type(name, " Groupe B ");
    await userEvent.click(dialog().getByRole("button", { name: "Rename" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(endpoints.updateClass).toHaveBeenCalledWith(5, { name: "Groupe B" });
    await waitFor(() => expect(endpoints.getClass).toHaveBeenCalledTimes(2));
  });

  it("won't rename to a blank name, and shows the backend's reason for a refusal", async () => {
    vi.mocked(endpoints.updateClass).mockRejectedValue(
      new ApiError(409, "A class 2BAC — Groupe C already exists.", "class_exists"),
    );
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const name = dialog().getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "   ");
    await userEvent.click(dialog().getByRole("button", { name: "Rename" }));
    expect(await dialog().findByText("Name is required")).toBeInTheDocument();
    expect(endpoints.updateClass).not.toHaveBeenCalled();

    await userEvent.clear(name);
    await userEvent.type(name, "Groupe C");
    await userEvent.click(dialog().getByRole("button", { name: "Rename" }));
    expect(await dialog().findByText("A class 2BAC — Groupe C already exists.")).toBeInTheDocument();

    await userEvent.click(dialog().getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(endpoints.getClass).toHaveBeenCalledTimes(1);
  });

  it("deletes the class once confirmed, and goes back to the classes", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Delete class" }));
    expect(confirm).toHaveBeenCalledWith("Delete this class? It must have no students.");
    expect(await screen.findByText("All the classes")).toBeInTheDocument();
    expect(endpoints.deleteClass).toHaveBeenCalledWith(5);
  });

  it("does nothing when the deletion isn't confirmed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Delete class" }));
    expect(endpoints.deleteClass).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "2BAC — Groupe A" })).toBeInTheDocument();
  });

  it("refuses to delete a class that still has students, with the backend's reason", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(endpoints.deleteClass).mockRejectedValue(
      new ApiError(409, "This class still has 3 students. Move them first.", "class_not_empty"),
    );
    await renderClass();
    await userEvent.click(screen.getByRole("button", { name: "Delete class" }));
    expect(await screen.findByText("This class still has 3 students. Move them first.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2BAC — Groupe A" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Delete class" })).toBeEnabled());
  });

  it("offline, shows the class but switches off every change", async () => {
    reportOffline();
    await renderClass();
    expect(screen.getByRole("button", { name: "Rename" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete class" })).toBeDisabled();
    expect(screen.queryByRole("link", { name: "Add student" })).toBeNull();
    expect(rosterList().getAllByRole("link")).toHaveLength(3);
  });
});
