import { useTranslation } from "react-i18next";
import { Spinner } from "./Spinner";

/** Centered loading indicator for the `loading` branch of an async read. */
export function LoadingState({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500 dark:text-slate-400">
      <Spinner />
      {label ?? t("common.loading")}
    </div>
  );
}
