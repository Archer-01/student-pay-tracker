import type { ReactNode } from "react";
import { Table, TBody, Td, Th, THead, Tr } from "./Table";

export type Column<T> = {
  /** Stable identity, and the label shown beside the value on a phone. */
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Rendered as the card's heading on a phone rather than as a labelled field. */
  primary?: boolean;
  /** Dropped from the card entirely — for columns that only earn their space in a wide table. */
  wideOnly?: boolean;
  align?: "left" | "right";
};

type Props<T> = {
  rows: T[];
  columns: Column<T>[];
  keyOf: (row: T) => string | number;
  /** Shown in place of the whole thing when there is nothing to list. */
  empty?: ReactNode;
  /** Per-row styling, applied to both the table row and the card. */
  rowClassName?: (row: T) => string;
};

/**
 * One list, two presentations: a table from the `sm` breakpoint up, stacked cards below it.
 *
 * A phone is 375px wide and these lists run to seven columns, so a table there is a sideways
 * scroll through the app's most-used screen. Cards drop the horizontal axis entirely: the row's
 * identity becomes a heading and everything else becomes a labelled line, which reads down the
 * page the way a phone wants to be read.
 *
 * Both presentations come from the same column definitions, so they cannot drift apart — the
 * failure mode of hand-writing a separate mobile layout is that one of them quietly stops being
 * updated.
 */
export function DataTable<T>({ rows, columns, keyOf, empty, rowClassName }: Props<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>;

  const cardColumns = columns.filter((c) => !c.wideOnly);
  const heading = cardColumns.filter((c) => c.primary);
  const fields = cardColumns.filter((c) => !c.primary);

  return (
    <>
      {/* Phone: one card per row. */}
      <ul className="space-y-2 sm:hidden">
        {rows.map((row) => (
          <li
            key={keyOf(row)}
            className={`rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 ${rowClassName?.(row) ?? ""}`}
          >
            {heading.map((c) => (
              <div key={c.key} className="mb-2 text-base font-medium">
                {c.cell(row)}
              </div>
            ))}
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5 text-sm">
              {fields.map((c) => (
                <div key={c.key} className="col-span-2 flex items-baseline justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{c.header}</dt>
                  <dd className="text-right">{c.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>

      {/* Tablet and up: the table, where the extra width is actually available. */}
      <div className="hidden sm:block">
        <Table>
          <THead>
            <Tr>
              {columns.map((c) => (
                <Th key={c.key} className={c.align === "right" ? "text-right" : undefined}>
                  {c.header}
                </Th>
              ))}
            </Tr>
          </THead>
          <TBody>
            {rows.map((row) => (
              <Tr key={keyOf(row)} className={rowClassName?.(row) ?? ""}>
                {columns.map((c) => (
                  <Td key={c.key} className={c.align === "right" ? "text-right" : undefined}>
                    {c.cell(row)}
                  </Td>
                ))}
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>
    </>
  );
}
