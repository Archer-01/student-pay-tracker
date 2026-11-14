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
  normal: "border-line bg-surface",
  alert: "border-transparent bg-warn-soft text-warn",
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
      className={`overflow-hidden rounded-2xl border ${tones[tone]} ${padded ? "p-4 sm:p-5" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
