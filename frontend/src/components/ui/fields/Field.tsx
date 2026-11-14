import type { ReactNode } from "react";

/** Shared label + hint + error scaffolding for all form fields. `htmlFor` ties the label to the input. */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-bold text-ink">
        {label}
      </label>
      {children}
      {hint && !error && <p className="mt-1.5 text-sm text-muted">{hint}</p>}
      {error && <p className="mt-1.5 text-sm font-bold text-bad">{error}</p>}
    </div>
  );
}
