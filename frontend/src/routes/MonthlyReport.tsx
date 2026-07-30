import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getMonthlyReport } from "../api/endpoints";
import { downloadFile } from "../api/client";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate } from "../lib/dates";
import { resolveErrorMessage } from "../lib/errors";
import { DriftBadge } from "../components/DriftBadge";
import { AsyncView, Button, Card, PageHeader, Select, Table, TBody, THead, Th, Td, Tr } from "../components/ui";

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function MonthlyReport() {
  const { t, i18n } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const state = useApi(() => getMonthlyReport(year, month), [year, month]);

  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloadError(null);
    try {
      const filename = `${t("report.pdfFilename", { year, month })}.pdf`;
      await downloadFile("/reports/monthly.pdf", filename, { year, month });
    } catch (err) {
      setDownloadError(resolveErrorMessage(err, t));
    }
  }

  // Localized month names (Jan…Dec) + a rolling range of recent years — works in every browser.
  const monthOptions = Array.from({ length: 12 }, (_, i) => ({
    value: String(i + 1),
    label: capitalize(
      new Intl.DateTimeFormat(i18n.language, { month: "long" }).format(new Date(2000, i, 1)),
    ),
  }));
  const yearOptions = Array.from({ length: 7 }, (_, i) => {
    const y = now.getFullYear() - i;
    return { value: String(y), label: String(y) };
  });

  const actions = (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-end gap-2">
        <Select
          id="report-month"
          label={t("report.monthLabel")}
          value={String(month)}
          onChange={(v) => setMonth(Number(v))}
          options={monthOptions}
        />
        <Select
          id="report-year"
          label={t("report.yearLabel")}
          value={String(year)}
          onChange={(v) => setYear(Number(v))}
          options={yearOptions}
        />
        <Button variant="secondary" onClick={handleDownload} className="mb-[1px]">
          {t("report.downloadPdf")}
        </Button>
      </div>
      {downloadError && <span className="text-xs text-rose-600 dark:text-rose-400">{downloadError}</span>}
    </div>
  );

  return (
    <div>
      <PageHeader title={t("pages.report")} actions={actions} />

      <AsyncView state={state} onRetry={state.reload}>
        {(report) => (
          <>
            <p className="-mt-4 mb-6 text-sm text-slate-400 dark:text-slate-500">
              {t("report.asOf", { date: formatDate(report.as_of) })}
            </p>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <StatTile label={t("report.totalCollected")}>{formatMoney(report.total_collected)}</StatTile>
              <StatTile label={t("report.totalOutstanding")}>{formatMoney(report.total_outstanding)}</StatTile>
            </div>

            {report.rows.length === 0 ? (
              <Card>
                <p className="py-6 text-center text-sm text-slate-500 dark:text-slate-400">{t("report.empty")}</p>
              </Card>
            ) : (
              <Table>
                <THead>
                  <Tr>
                    <Th>{t("report.columns.name")}</Th>
                    <Th>{t("report.columns.status")}</Th>
                    <Th>{t("report.columns.fee")}</Th>
                    <Th>{t("report.columns.collected")}</Th>
                    <Th>{t("report.columns.drift")}</Th>
                    <Th>{t("report.columns.outstanding")}</Th>
                  </Tr>
                </THead>
                <TBody>
                  {report.rows.map((row) => (
                    <Tr key={row.student_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                      <Td>
                        <Link
                          to={`/students/${row.student_id}`}
                          className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                        >
                          {row.name}
                        </Link>
                      </Td>
                      <Td className="text-slate-600 dark:text-slate-300">{t(`status.${row.status}`)}</Td>
                      <Td className="text-slate-600 dark:text-slate-300">{formatMoney(row.fee)}</Td>
                      <Td className="text-slate-600 dark:text-slate-300">{formatMoney(row.collected)}</Td>
                      <Td>
                        <DriftBadge drift={row.cumulative_drift} />
                      </Td>
                      <Td className="text-slate-600 dark:text-slate-300">{formatMoney(row.outstanding)}</Td>
                    </Tr>
                  ))}
                </TBody>
              </Table>
            )}
          </>
        )}
      </AsyncView>
    </div>
  );
}

function StatTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Card>
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">{children}</p>
    </Card>
  );
}
