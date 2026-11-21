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
          className="min-h-11 rounded-xl border border-line bg-surface px-4 text-sm font-bold text-brand hover:bg-brand-soft"
        >
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
