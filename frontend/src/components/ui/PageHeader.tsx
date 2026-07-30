import type { ReactNode } from "react";

/** Consistent page heading with an optional right-aligned actions slot (filters, buttons). */
export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex items-center justify-between gap-4">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
