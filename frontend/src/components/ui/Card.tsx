import type { ReactNode } from "react";

/** Bordered white section wrapper. Set `padded={false}` when the child manages its own padding (e.g. tables). */
export function Card({
  children,
  padded = true,
  className = "",
}: {
  children: ReactNode;
  padded?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 ${padded ? "p-5" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
