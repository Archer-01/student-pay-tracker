import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import * as endpoints from "../api/endpoints";
import { ApiError } from "../api/client";
import { reportOffline, resetConnectivity } from "../lib/connectivity";
import { ClassesList } from "./ClassesList";

function schoolClass(over: Partial<Record<string, unknown>>) {
  return {
    id: 1, level: "TC", name: "Groupe A", created_at: "2026-09-01T00:00:00", student_count: 0,
    cumulative_drift: 0, ...over,
  };
}

// The server returns classes in school order; "1BAC" would sort before "2AC" alphabetically.
const classes = [
  schoolClass({ id: 2, level: "2AC", name: "Groupe B", student_count: 1, cumulative_drift: 0 }),
  schoolClass({ id: 7, level: "1BAC", name: "Sciences", student_count: 14, cumulative_drift: 23 }),
];

beforeEach(() => {
  vi.spyOn(endpoints, "listClasses").mockResolvedValue(classes as never);
  vi.spyOn(endpoints, "createClass").mockResolvedValue({} as never);
});

afterEach(() => {
  resetConnectivity();
  vi.restoreAllMocks();
});

const list = () => within(screen.getByRole("list", { name: "Classes" }));
const dialog = () => within(screen.getByRole("dialog"));

async function openCreate() {
  renderWithProviders(<ClassesList />);
  await screen.findByText("Sciences");
  await userEvent.click(screen.getByRole("button", { name: "New class" }));
}

describe("ClassesList", () => {
  it("lists classes in school order, each with its size and lateness, linking to the class", async () => {
    renderWithProviders(<ClassesList />);
    await screen.findByText("Sciences");
    const rows = list().getAllByRole("link");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("2AC");
    expect(rows[0]).toHaveTextContent("Groupe B");
    expect(rows[0]).toHaveTextContent("1 student");
    expect(rows[0]).not.toHaveTextContent("late");
    expect(rows[0]).toHaveAttribute("href", "/settings/classes/2");
    expect(rows[1]).toHaveTextContent("1BAC");
    expect(rows[1]).toHaveTextContent("14 students · 23 days late");
    expect(rows[1]).toHaveAttribute("href", "/settings/classes/7");
    expect(screen.getByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
  });

  it("says so when there are no classes yet", async () => {
    vi.mocked(endpoints.listClasses).mockResolvedValue([] as never);
    renderWithProviders(<ClassesList />);
    expect(await screen.findByText("No classes yet. Create one to start grouping students.")).toBeInTheDocument();
  });

  it("shows a failed load and fetches again on Retry", async () => {
    vi.mocked(endpoints.listClasses).mockRejectedValueOnce(new ApiError(500, "Server unavailable"));
    renderWithProviders(<ClassesList />);
    expect(await screen.findByText("Server unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Sciences")).toBeInTheDocument();
    expect(endpoints.listClasses).toHaveBeenCalledTimes(2);
  });

  it("creates a class at the chosen level, trimmed, then refreshes the list", async () => {
    await openCreate();
    expect(dialog().getByLabelText("Level")).toHaveValue("1AC");
    await userEvent.selectOptions(dialog().getByLabelText("Level"), "TC");
    await userEvent.type(dialog().getByLabelText("Name"), "  Groupe A  ");
    await userEvent.click(dialog().getByRole("button", { name: "New class" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(endpoints.createClass).toHaveBeenCalledWith({ level: "TC", name: "Groupe A" });
    await waitFor(() => expect(endpoints.listClasses).toHaveBeenCalledTimes(2));
  });

  it("asks for a name rather than sending a blank one", async () => {
    await openCreate();
    await userEvent.type(dialog().getByLabelText("Name"), "   ");
    await userEvent.click(dialog().getByRole("button", { name: "New class" }));
    expect(await dialog().findByText("Name is required")).toBeInTheDocument();
    expect(endpoints.createClass).not.toHaveBeenCalled();
  });

  it("shows the backend's reason when the class already exists, and keeps the form open", async () => {
    vi.mocked(endpoints.createClass).mockRejectedValue(
      new ApiError(409, "A class TC — Groupe A already exists.", "class_exists"),
    );
    await openCreate();
    await userEvent.type(dialog().getByLabelText("Name"), "Groupe A");
    await userEvent.click(dialog().getByRole("button", { name: "New class" }));
    expect(await dialog().findByText("A class TC — Groupe A already exists.")).toBeInTheDocument();
    expect(endpoints.listClasses).toHaveBeenCalledTimes(1);
  });

  it("puts a validation error on the field it is about", async () => {
    vi.mocked(endpoints.createClass).mockRejectedValue(
      new ApiError(422, [{ loc: ["body", "name"], msg: "String should have at most 50 characters", type: "string_too_long" }]),
    );
    await openCreate();
    await userEvent.type(dialog().getByLabelText("Name"), "Groupe A");
    await userEvent.click(dialog().getByRole("button", { name: "New class" }));
    expect(await dialog().findByText("String should have at most 50 characters")).toBeInTheDocument();
  });

  it("falls back to a generic message for an unexpected failure", async () => {
    vi.mocked(endpoints.createClass).mockRejectedValue(new TypeError("boom"));
    await openCreate();
    await userEvent.type(dialog().getByLabelText("Name"), "Groupe A");
    await userEvent.click(dialog().getByRole("button", { name: "New class" }));
    expect(await dialog().findByText("Something went wrong. Please try again.")).toBeInTheDocument();
  });

  it("closes the form without creating anything", async () => {
    await openCreate();
    await userEvent.click(dialog().getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(endpoints.createClass).not.toHaveBeenCalled();
  });

  it("can't create a class offline, but still lists them", async () => {
    reportOffline();
    renderWithProviders(<ClassesList />);
    await screen.findByText("Sciences");
    expect(screen.getByRole("button", { name: "New class" })).toBeDisabled();
  });
});
