import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";

/** Neutral "nothing here yet" placeholder with an optional action slot. */
export function EmptyState({ message, action }: { message?: string; action?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <p className="text-sm text-slate-500 dark:text-slate-400">{message ?? t("common.empty")}</p>
      {action}
    </div>
  );
}
