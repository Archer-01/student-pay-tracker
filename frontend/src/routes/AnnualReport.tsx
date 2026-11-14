import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getAnnualReport } from "../api/endpoints";
import { downloadFile } from "../api/client";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { resolveErrorMessage } from "../lib/errors";
import { usePaymentsVersion } from "../lib/paymentSheetContext";
import { ReportTabs } from "../components/ReportTabs";
import { AsyncView, Button } from "../components/ui";
import { BarChart, Figure, Stepper } from "../components/report";
import { ShareSplit } from "../components/ShareSplit";

/** Bilan › Année: the calendar year's takings, month by month, with arrows between years. */
export function AnnualReport() {
  const { t, i18n } = useTranslation();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Refreshes after a payment taken from the shared sheet, wherever it was opened.
  const paymentsVersion = usePaymentsVersion();
  const state = useApi(() => getAnnualReport(year), [year, paymentsVersion]);

  // Month names come from the browser's locale data rather than a hand-kept list.
  const monthName = (month: number, style: "long" | "narrow" = "long") =>
    new Intl.DateTimeFormat(i18n.language, { month: style }).format(new Date(2000, month - 1, 1));
  const capitalized = (month: number) => {
    const name = monthName(month);
    return name.charAt(0).toLocaleUpperCase(i18n.language) + name.slice(1);
  };

  async function handleDownload() {
    setDownloadError(null);
    try {
      await downloadFile("/reports/annual.pdf", `annual-${year}.pdf`, { year });
    } catch (err) {
      setDownloadError(resolveErrorMessage(err, t));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <ReportTabs />
      <Stepper
        label={String(year)}
        previousLabel={t("reports.previousYear")}
        nextLabel={t("reports.nextYear")}
        onPrevious={() => setYear(year - 1)}
        onNext={() => setYear(year + 1)}
        canGoNext={year < thisYear}
      />

      <AsyncView state={state} onRetry={state.reload}>
        {(report) => {
          const earning = report.months.filter((m) => Number(m.collected) > 0);
          const best = earning.reduce(
            (a, b) => (Number(b.collected) > Number(a?.collected ?? 0) ? b : a),
            earning[0],
          );
          // Averaged over months that earned: a year that only ran from September would
          // otherwise look like it took a third of what it did. Display only; never sent back.
          const average = earning.length > 0 ? Number(report.total_collected) / earning.length : 0;

          return (
            <>
              <section className="grid grid-cols-2 gap-3">
                <Figure label={t("annual.total")} value={formatMoney(report.total_collected)} />
                <Figure label={t("annual.payments")} value={String(report.payments_count)} />
                <Figure
                  label={t("annual.average")}
                  value={formatMoney(average.toFixed(2))}
                  hint={t("annual.averageHint")}
                />
                <Figure label={t("annual.best")} value={best ? capitalized(best.month) : "—"} />
              </section>

              <ShareSplit share={report.share} />

              {report.payments_count === 0 ? (
                <p className="rounded-2xl border border-line bg-surface p-4 text-muted">{t("annual.empty")}</p>
              ) : (
                <>
                  <section className="rounded-2xl border border-line bg-surface p-4">
                    <BarChart
                      bars={report.months.map((m) => ({
                        key: String(m.month),
                        label: monthName(m.month, "narrow"),
                        title: `${capitalized(m.month)} · ${formatMoney(m.collected)}`,
                        value: Number(m.collected),
                        selected: best?.month === m.month,
                      }))}
                    />
                  </section>
                  <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
                    {report.months.map((m) => (
                      <li key={m.month} className="flex min-h-14 items-center justify-between gap-3 px-4 py-2">
                        <span className="font-bold">{capitalized(m.month)}</span>
                        <span className="text-right">
                          <span className={`block font-bold tabular-nums ${Number(m.collected) > 0 ? "" : "text-muted"}`}>
                            {formatMoney(m.collected)}
                          </span>
                          <span className="block text-sm text-muted">
                            {t("student.paymentsCount", { count: m.payments_count })}
                          </span>
                          {Number(m.share.percent) > 0 && Number(m.collected) > 0 && (
                            <span className="block text-sm text-muted">
                              {t("share.yoursShort", { amount: formatMoney(m.share.teacher) })}
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          );
        }}
      </AsyncView>

      <Button variant="secondary" onClick={handleDownload} className="sm:self-start">
        {t("annual.downloadPdf")}
      </Button>
      {downloadError && <p className="text-sm font-bold text-bad">{downloadError}</p>}
    </div>
  );
}
