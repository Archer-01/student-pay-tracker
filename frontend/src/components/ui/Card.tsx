import type { ReactNode } from "react";

type Tone = "normal" | "alert";

/**
 * Bordered section wrapper. Set `padded={false}` when the child manages its own padding (e.g.
 * tables), and `tone="alert"` for something that needs noticing.
 *
 * `tone` is a variant rather than a `className` override on purpose: Tailwind resolves classes of
 * equal specificity by their order in the generated stylesheet, not the order they appear in the
 * attribute, so passing `bg-amber-50` alongside the default `bg-white` is a coin flip.
 */
const tones: Record<Tone, string> = {
  normal: "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900",
  alert: "border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40",
};

export function Card({
  children,
  padded = true,
  tone = "normal",
  className = "",
}: {
  children: ReactNode;
  padded?: boolean;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-lg border ${tones[tone]} ${padded ? "p-5" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
