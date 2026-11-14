import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Avatar } from "./people";

/**
 * One student on one line: initials, the name, a grey line of facts, and something on the right
 * (usually an `OwedPill`). The same row everywhere a list of students appears, so a teacher
 * learns to read it once.
 */
export function StudentRow({
  to,
  name,
  facts,
  right,
}: {
  to: string;
  name: string;
  /** Short facts joined into the grey line, e.g. months unpaid, lateness, class. Falsy ones are skipped. */
  facts: (string | null | undefined | false)[];
  right?: ReactNode;
}) {
  return (
    <li>
      <Link to={to} className="flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-ground">
        <Avatar name={name} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-bold">{name}</span>
          <span className="block truncate text-sm text-muted">{facts.filter(Boolean).join(" · ")}</span>
        </span>
        {right}
      </Link>
    </li>
  );
}

/** The list a set of `StudentRow`s sits in. */
export function StudentRows({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <ul aria-label={label} className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
      {children}
    </ul>
  );
}
