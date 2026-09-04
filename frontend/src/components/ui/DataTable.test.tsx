import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import { DataTable, type Column } from "./DataTable";

type Row = { id: number; name: string; owed: string; note: string };

const rows: Row[] = [
  { id: 1, name: "Amina Benali", owed: "3900.00", note: "wide only" },
  { id: 2, name: "Omar Tazi", owed: "960.00", note: "wide only" },
];

const columns: Column<Row>[] = [
  { key: "name", header: "Name", primary: true, cell: (r) => r.name },
  { key: "owed", header: "Owed", align: "right", cell: (r) => r.owed },
  { key: "note", header: "Note", wideOnly: true, cell: (r) => r.note },
];

describe("DataTable", () => {
  it("renders a table for wide screens", () => {
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Amina Benali")).toBeInTheDocument();
    expect(table.getByText("3900.00")).toBeInTheDocument();
  });

  it("renders one card per row for phones", () => {
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    // The card list is the only `list` in the output; the table has its own role.
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(2);
  });

  it("labels each value on the card, since there are no column headers to read across", () => {
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    const card = within(screen.getAllByRole("listitem")[0]);
    expect(card.getByText("Owed")).toBeInTheDocument();
    expect(card.getByText("3900.00")).toBeInTheDocument();
  });

  it("drops wideOnly columns from the card but keeps them in the table", () => {
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    expect(within(screen.getAllByRole("listitem")[0]).queryByText("wide only")).toBeNull();
    expect(within(screen.getByRole("table")).getAllByText("wide only")).toHaveLength(2);
  });

  it("does not label the primary column — it is the card's heading", () => {
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    expect(within(screen.getAllByRole("listitem")[0]).queryByText("Name")).toBeNull();
  });

  it("shows the empty state instead of an empty shell", () => {
    renderWithProviders(
      <DataTable rows={[]} columns={columns} keyOf={(r) => r.id} empty={<p>Nobody yet</p>} />,
    );
    expect(screen.getByText("Nobody yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("still renders headers when there are rows but no empty state given", () => {
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    expect(within(screen.getByRole("table")).getByText("Name")).toBeInTheDocument();
  });

  it("keeps both presentations in step from one column definition", () => {
    // The reason for a shared definition: a hand-written mobile layout drifts when only one of
    // the two gets updated.
    renderWithProviders(<DataTable rows={rows} columns={columns} keyOf={(r) => r.id} />);
    for (const row of rows) {
      expect(screen.getAllByText(row.name).length).toBe(2); // once per presentation
    }
  });
});
