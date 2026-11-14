import { useTranslation } from "react-i18next";

/**
 * What a screen shows while its first load is on the way: grey shapes in the outline of what is
 * coming (two figures, a few rows), so the page doesn't jump when the data lands. Only for the
 * first load: a refresh keeps the current data showing instead (see `useApi`).
 */
export function Skeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" className="flex animate-pulse flex-col gap-4">
      <span className="sr-only">{t("common.loading")}</span>
      <div className="grid grid-cols-2 gap-3">
        <div className="h-24 rounded-2xl bg-line" />
        <div className="h-24 rounded-2xl bg-line" />
      </div>
      <div className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-4">
            <div className="h-10 w-10 shrink-0 rounded-full bg-line" />
            <div className="flex flex-1 flex-col gap-2">
              <div className="h-3.5 w-2/5 rounded bg-line" />
              <div className="h-3 w-3/5 rounded bg-line" />
            </div>
            <div className="h-7 w-16 rounded-full bg-line" />
          </div>
        ))}
      </div>
    </div>
  );
}
