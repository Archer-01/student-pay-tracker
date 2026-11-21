import { useTranslation } from "react-i18next";

/**
 * How a student usually pays, from the server's average days late over their last six payments
 * (`average_days_late`). A day or two late is normal life; a week is a habit worth seeing.
 */
export type Punctuality = "on_time" | "bit_late" | "often_late";

export function punctualityOf(averageDaysLate: number | null | undefined): Punctuality | null {
  if (averageDaysLate === null || averageDaysLate === undefined) return null;
  if (averageDaysLate <= 2) return "on_time";
  if (averageDaysLate <= 7) return "bit_late";
  return "often_late";
}

/** Each group's status tone, as on the rest of the app's pills. */
export const punctualityTone: Record<Punctuality, "ok" | "warn" | "bad"> = {
  on_time: "ok",
  bit_late: "warn",
  often_late: "bad",
};

/** The words under a name, short enough for a phone row: "Paie à l'heure", "Retard moyen : 4 j". */
export function usePunctualityText(): (averageDaysLate: number) => string {
  const { t } = useTranslation();
  return (days) => (days === 0 ? t("punctuality.paysOnTime") : t("punctuality.average", { count: days }));
}
