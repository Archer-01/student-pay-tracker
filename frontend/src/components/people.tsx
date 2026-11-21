import type { PriceStatus } from "../api/types";
import { useTranslation } from "react-i18next";
import { formatMoney } from "../lib/money";
import { useFlashOnChange } from "../lib/useFlashOnChange";
import { punctualityOf, punctualityTone } from "../lib/punctuality";

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
  priceStatus,
}: {
  monthsOverdue: number;
  amountOwed: string;
  priceStatus: PriceStatus;
}) {
  const { t } = useTranslation();
  let tone: keyof typeof tones;
  let label: string;
  if (monthsOverdue > 0) {
    // The amount alone: how many months goes on the line under the name, where there is room.
    tone = monthsOverdue === 1 ? "warn" : "bad";
    label = formatMoney(amountOwed);
  } else if (priceStatus === "priced") {
    tone = "ok";
    label = t("owed.paidUp");
  } else {
    // Free on purpose and not set up yet look alike but mean different things (decision 0011).
    tone = "off";
    label = t(priceStatus === "free" ? "owed.free" : "owed.noPrice");
  }
  return <PillText tone={tone} label={label} />;
}

/** How a student usually pays, as a pill: "À l'heure", "Un peu tard", "Souvent tard". */
export function PunctualityPill({ averageDaysLate }: { averageDaysLate: number | null }) {
  const { t } = useTranslation();
  const group = punctualityOf(averageDaysLate);
  if (!group) return null;
  return <PillText tone={punctualityTone[group]} label={t(`punctuality.${group}`)} />;
}

function PillText({ tone, label }: { tone: keyof typeof tones; label: string }) {
  const { flashing, done } = useFlashOnChange(label);
  return (
    <span
      onAnimationEnd={done}
      className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1 text-sm font-bold tabular-nums ${tones[tone]} ${
        flashing ? "animate-paid-pop" : ""
      }`}
    >
      {label}
    </span>
  );
}
