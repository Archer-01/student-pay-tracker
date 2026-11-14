import { useTranslation } from "react-i18next";

/** The facts most rows lead with: months unpaid, then lateness, when there are any. */
export function useMoneyFacts() {
  const { t } = useTranslation();
  return ({ monthsOverdue, drift }: { monthsOverdue: number; drift: number }) => [
    monthsOverdue > 0 && t("owed.monthsUnpaid", { count: monthsOverdue }),
    drift > 0 && t("home.lateTotal", { count: drift }),
  ];
}
