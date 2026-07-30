import { useTranslation } from "react-i18next";

/** Arrears indicator: unpaid billing cycles due by now. Complements DriftBadge (habit vs debt). */
export function OverdueBadge({ monthsOverdue }: { monthsOverdue: number }) {
  const { t } = useTranslation();

  const tone =
    monthsOverdue === 0
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
      : monthsOverdue <= 2
        ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300";

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tone}`}>
      {monthsOverdue === 0 ? t("overdue.paidUp") : t("overdue.monthsBehind", { count: monthsOverdue })}
    </span>
  );
}
