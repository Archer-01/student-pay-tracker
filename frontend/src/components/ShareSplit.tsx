import { useTranslation } from "react-i18next";
import type { Share } from "../api/types";
import { formatMoney, formatPercent } from "../lib/money";

/**
 * What came in, split between the teacher and the school owner: a bar in proportion, then the
 * two amounts. The figures come from the server (it does the money arithmetic); `Number` here
 * only sizes the bar. Renders nothing when there is no share to give.
 */
export function ShareSplit({ share }: { share: Share }) {
  const { t } = useTranslation();
  const percent = Number(share.percent);
  if (!(percent > 0)) return null;
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4">
      <h2 className="font-bold">{t("share.title")}</h2>
      <div aria-hidden="true" className="flex h-3 overflow-hidden rounded-full bg-school">
        <span className="block h-full rounded-r-full bg-brand" style={{ width: `${100 - percent}%` }} />
      </div>
      <dl className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <dt className="flex items-center gap-2">
            <span aria-hidden="true" className="h-3 w-3 rounded-sm bg-brand" />
            {t("share.yours")}
          </dt>
          <dd className="font-display text-xl font-extrabold tabular-nums">{formatMoney(share.teacher)}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 text-muted">
          <dt className="flex items-center gap-2">
            <span aria-hidden="true" className="h-3 w-3 rounded-sm bg-school" />
            {t("share.school", { percent: formatPercent(share.percent) })}
          </dt>
          <dd className="font-bold tabular-nums">{formatMoney(share.school)}</dd>
        </div>
      </dl>
    </section>
  );
}
