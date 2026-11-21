import type { ReactNode } from "react";

/** A radio button that looks like a pill: easier to hit, and all choices visible at once. */
export function Chip({
  name,
  checked,
  onChange,
  children,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  children: ReactNode;
}) {
  return (
    <label
      className={`flex min-h-11 cursor-pointer items-center rounded-full border-2 px-4 font-bold has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand ${
        checked ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink"
      }`}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className="sr-only" />
      {children}
    </label>
  );
}
