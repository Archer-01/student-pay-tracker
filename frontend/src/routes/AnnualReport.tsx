import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getAnnualReport } from "../api/endpoints";
import { downloadFile } from "../api/client";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { resolveErrorMessage } from "../lib/errors";
import { ReportTabs } from "../components/ReportTabs";
import {
  AsyncView,
  Button,
  Card,
  PageHeader,
  Select,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
} from "../components/ui";

/** The last few years, newest first — enough to look back without a date picker. */
function yearOptions(): { value: string; label: string }[] {
  const now = new Date().getFullYear();
  return Array.from({ length: 6 }, (_, i) => String(now - i)).map((y) => ({
    value: y,
    label: y,
  }));
}

export function AnnualReport() {
  const { t, i18n } = useTranslation();
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const state = useApi(() => getAnnualReport(Number(year)), [year]);

  // Month names come from the browser's locale data rather than a hand-kept list.
  const monthName = (month: number) =>
    new Intl.DateTimeFormat(i18n.language, { month: "long" }).format(new Date(2000, month - 1, 1));

  async function handleDownload() {
    setDownloadError(null);
    try {
      await downloadFile("/reports/annual.pdf", `annual-${year}.pdf`, { year });
    } catch (err) {
      setDownloadError(resolveErrorMessage(err, t));
    }
  }

  const actions = (
    <div className="flex items-end gap-2">
      <Select
        id="annual-year"
        label={t("annual.year")}
        value={year}
        onChange={setYear}
        options={yearOptions()}
      />
      <Button variant="secondary" onClick={handleDownload} className="mb-[1px]">
        {t("annual.downloadPdf")}
      </Button>
    </div>
  );

  return (
    <div>
      <ReportTabs />
      <PageHeader title={t("pages.annual")} actions={actions} />
      {downloadError && (
        <p className="mb-4 text-sm text-rose-600 dark:text-rose-400">{downloadError}</p>
      )}

      <AsyncView state={state} onRetry={state.reload}>
        {(report) => {
          const earning = report.months.filter((m) => Number(m.collected) > 0);
          const best = earning.reduce(
            (a, b) => (Number(b.collected) > Number(a?.collected ?? 0) ? b : a),
            earning[0],
          );
          // Averaged over months that earned: a year that only ran from September would
          // otherwise look like it took a third of what it did.
          const average =
            earning.length > 0 ? Number(report.total_collected) / earning.length : 0;
          const peak = Math.max(...report.months.map((m) => Number(m.collected)), 0);

          return (
            <>
              <Card className="mb-6">
                <div className="flex flex-wrap items-start gap-8">
                  <Figure label={t("annual.total")} value={formatMoney(report.total_collected)} />
                  <Figure label={t("annual.payments")} value={String(report.payments_count)} />
                  <Figure
                    label={t("annual.average")}
                    value={formatMoney(average.toFixed(2))}
                    hint={t("annual.averageHint")}
                  />
                  <Figure
                    label={t("annual.best")}
                    value={best ? monthName(best.month) : "—"}
                  />
                </div>
              </Card>

              {report.payments_count === 0 ? (
                <Card>
                  <p className="text-sm text-slate-500 dark:text-slate-400">{t("annual.empty")}</p>
                </Card>
              ) : (
                <Table>
                  <THead>
                    <Tr>
                      <Th>{t("annual.month")}</Th>
                      <Th>{t("annual.collected")}</Th>
                      <Th>{t("annual.payments")}</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {report.months.map((m) => (
                      <Tr key={m.month}>
                        <Td className="text-slate-600 capitalize dark:text-slate-300">
                          {monthName(m.month)}
                        </Td>
                        <Td>
                          <div className="flex items-center gap-2">
                            <span
                              className={
                                Number(m.collected) > 0
                                  ? "font-medium text-slate-900 dark:text-slate-100"
                                  : "text-slate-400 dark:text-slate-500"
                              }
                            >
                              {formatMoney(m.collected)}
                            </span>
                            {/* A bar relative to the best month, so the shape of the year reads
                                at a glance without a chart library. Hidden on a phone, where 120px
                                of decoration would push the figures themselves off the screen. */}
                            {peak > 0 && (
                              <span
                                aria-hidden
                                className="hidden h-1.5 rounded-full bg-indigo-500/70 sm:inline-block dark:bg-indigo-400/70"
                                style={{ width: `${(Number(m.collected) / peak) * 120}px` }}
                              />
                            )}
                          </div>
                        </Td>
                        <Td className="text-slate-600 dark:text-slate-300">{m.payments_count}</Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              )}
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">{hint}</p>}
    </div>
  );
}
