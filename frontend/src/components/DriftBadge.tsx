import { useTranslation } from "react-i18next";

/** Drift is cumulative days late; higher is worse. Color bands make chronic latecomers pop in tables. */
export function DriftBadge({ drift }: { drift: number }) {
  const { t } = useTranslation();

  const tone =
    drift === 0
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
      : drift <= 14
        ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300";

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tone}`}>
      {drift === 0 ? t("drift.onTrack") : t("drift.late", { count: drift })}
    </span>
  );
}
