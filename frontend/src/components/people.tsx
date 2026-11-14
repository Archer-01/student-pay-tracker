import { useTranslation } from "react-i18next";
import { formatMoney } from "../lib/money";

/** "Amina Benali" → "AB"; "Fatima Zahra El Idrissi" → "FZ". */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

export function Avatar({ name, size = "md" }: { name: string; size?: "md" | "lg" }) {
  const dims = size === "lg" ? "h-14 w-14 text-lg" : "h-10 w-10 text-sm";
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full bg-brand-soft font-bold text-brand ${dims}`}
    >
      {initials(name)}
    </span>
  );
}

const tones = {
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  off: "bg-off-soft text-off",
} as const;

/**
 * What a student owes, in words and colour together: the amount (amber for one month, red for two
 * or more), green "À jour", or grey "Sans tarif". Colour is never the only signal: the row it sits
 * on also says how many months.
 */
export function OwedPill({
  monthsOverdue,
  amountOwed,
  monthlyPrice,
}: {
  monthsOverdue: number;
  amountOwed: string;
  monthlyPrice: string;
}) {
  const { t } = useTranslation();
  let tone: keyof typeof tones;
  let label: string;
  if (monthsOverdue > 0) {
    // The amount alone: how many months goes on the line under the name, where there is room.
    tone = monthsOverdue === 1 ? "warn" : "bad";
    label = formatMoney(amountOwed);
  } else if (Number(monthlyPrice) > 0) {
    tone = "ok";
    label = t("owed.paidUp");
  } else {
    tone = "off";
    label = t("owed.noPrice");
  }
  return (
    <span className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1 text-sm font-bold tabular-nums ${tones[tone]}`}>
      {label}
    </span>
  );
}
