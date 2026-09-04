import type { ReactNode } from "react";

/**
 * Page heading with an optional actions slot for filters and buttons.
 *
 * Stacked on a phone and side by side from `sm` up: the students page carries a search box, two
 * filters and a button, which on a 375px screen would otherwise be crushed against the title.
 */
export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{title}</h1>
      {actions && <div className="flex flex-wrap items-end gap-2">{actions}</div>}
    </div>
  );
}
