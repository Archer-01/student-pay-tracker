import type { ButtonHTMLAttributes } from "react";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-ink hover:opacity-90",
  secondary: "border border-line bg-surface text-brand hover:bg-brand-soft",
  ghost: "text-muted hover:bg-ground hover:text-ink",
  danger: "bg-bad text-white hover:opacity-90 dark:text-ground",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  /** Shows a spinner and disables the button while a mutation is in flight. */
  pending?: boolean;
};

export function Button({ variant = "primary", pending = false, disabled, className = "", children, ...rest }: Props) {
  return (
    <button
      disabled={disabled || pending}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2 font-bold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...rest}
    >
      {pending && <Spinner />}
      {children}
    </button>
  );
}
