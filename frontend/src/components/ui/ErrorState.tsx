import { useTranslation } from "react-i18next";

/** Error branch of an async read. Pass the flattened message (e.g. `ApiError.message`); optional retry. */
export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <p className="text-sm text-rose-600 dark:text-rose-400">{message ?? t("common.error")}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
