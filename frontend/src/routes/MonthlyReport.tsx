import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getAnnualReport, getMonthlyReport } from "../api/endpoints";
import { downloadFile } from "../api/client";
import type { AnnualReport, MonthlyReport as MonthlyReportData } from "../api/types";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate, formatMonthTitle } from "../lib/dates";
import { resolveErrorMessage } from "../lib/errors";
import { usePaymentsVersion } from "../lib/paymentSheetContext";
import { ReportTabs } from "../components/ReportTabs";
import { AsyncView, Button } from "../components/ui";
import { BarChart, Figure, Stepper } from "../components/report";
import { StudentRow, StudentRows } from "../components/StudentRow";

type YearMonth = { year: number; month: number };

const key = ({ year, month }: YearMonth) => `${year}-${String(month).padStart(2, "0")}`;
const shift = ({ year, month }: YearMonth, by: number): YearMonth => {
  const index = year * 12 + (month - 1) + by;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
};

/**
 * Bilan › Mois: what came in this month and what is still owed, the school year as bars (tap
 * one to open that month), then each student on one line. Arrows step through months instead of
 * two dropdowns; nothing after the current month, which has no figures yet.
 *
 * "Impayés" carries the date it is counted at. The month's figure is counted at the month's end,
 * Accueil's at today, and without the date the two looked like they disagreed.
 */
export function MonthlyReport() {
  const { t } = useTranslation();
  const now = new Date();
  const current: YearMonth = { year: now.getFullYear(), month: now.getMonth() + 1 };
  const [selected, setSelected] = useState<YearMonth>(current);
  const { year, month } = selected;
  const schoolYear = month >= 9 ? year : year - 1;

  // Refreshes after a payment taken from the shared sheet, wherever it was opened.
  const paymentsVersion = usePaymentsVersion();
  const report = useApi(() => getMonthlyReport(year, month), [year, month, paymentsVersion]);
  // The school year spans two calendar years, which the API reports separately.
  const annual = useApi(
    () => Promise.all([getAnnualReport(schoolYear), getAnnualReport(schoolYear + 1)]),
    [schoolYear, paymentsVersion],
  );
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

  return (
    <div className="flex flex-col gap-5">
      <ReportTabs />
      <Stepper
        label={formatMonthTitle(key(selected))}
        previousLabel={t("reports.previousMonth")}
        nextLabel={t("reports.nextMonth")}
        onPrevious={() => setSelected(shift(selected, -1))}
        onNext={() => setSelected(shift(selected, 1))}
        canGoNext={key(selected) < key(current)}
      />

      <AsyncView state={report} onRetry={report.reload}>
        {(data) => (
          <>
            <section className="grid grid-cols-2 gap-3">
              <Figure label={t("report.totalCollected")} value={formatMoney(data.total_collected)} />
              <Figure
                label={t("home.outstanding", { date: formatDate(data.as_of) })}
                value={formatMoney(data.total_outstanding)}
                alarming={Number(data.total_outstanding) > 0}
              />
            </section>

            {annual.status === "success" && (
              <section className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4">
                <h2 className="font-bold">{t("student.schoolYear", { from: schoolYear, to: schoolYear + 1 })}</h2>
                <SchoolYearBars
                  years={annual.data}
                  startYear={schoolYear}
                  selected={key(selected)}
                  latest={key(current)}
                  onSelect={(ym) => setSelected({ year: Number(ym.slice(0, 4)), month: Number(ym.slice(5, 7)) })}
                />
              </section>
            )}

            <PerStudent data={data} />
          </>
        )}
      </AsyncView>

      <Button variant="secondary" onClick={handleDownload} className="sm:self-start">
        {t("report.downloadPdf")}
      </Button>
      {downloadError && <p className="text-sm font-bold text-bad">{downloadError}</p>}
    </div>
  );
}

function SchoolYearBars({
  years,
  startYear,
  selected,
  latest,
  onSelect,
}: {
  years: [AnnualReport, AnnualReport];
  startYear: number;
  selected: string;
  latest: string;
  onSelect: (ym: string) => void;
}) {
  const { i18n } = useTranslation();
  const months = Array.from({ length: 12 }, (_, i) => {
    const month = ((8 + i) % 12) + 1;
    const year = month >= 9 ? startYear : startYear + 1;
    const report = month >= 9 ? years[0] : years[1];
    return { ym: `${year}-${String(month).padStart(2, "0")}`, collected: report.months[month - 1]?.collected ?? "0" };
  });
  const letter = (ym: string) =>
    new Intl.DateTimeFormat(i18n.language, { month: "narrow" }).format(new Date(`${ym}-01T00:00:00`));
  return (
    <BarChart
      bars={months.map((m) => ({
        key: m.ym,
        label: letter(m.ym),
        title: `${formatMonthTitle(m.ym)} · ${formatMoney(m.collected)}`,
        value: Number(m.collected),
        selected: m.ym === selected,
      }))}
      onSelect={(ym) => {
        // Months still to come can't be opened: there is nothing in them yet.
        if (ym <= latest) onSelect(ym);
      }}
    />
  );
}

/** Each student on one line: what they paid this month, and what they still owe. */
function PerStudent({ data }: { data: MonthlyReportData }) {
  const { t } = useTranslation();
  const rows = [...data.rows].sort(
    (a, b) => Number(b.outstanding) - Number(a.outstanding) || a.name.localeCompare(b.name),
  );
  if (rows.length === 0) {
    return <p className="rounded-2xl border border-line bg-surface p-4 text-muted">{t("report.empty")}</p>;
  }
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">{t("reports.byStudent")}</h2>
      <StudentRows label={t("reports.byStudent")}>
        {rows.map((row) => (
          <StudentRow
            key={row.student_id}
            to={`/students/${row.student_id}`}
            name={row.name}
            facts={[
              Number(row.collected) > 0
                ? t("reports.paid", { amount: formatMoney(row.collected) })
                : t("reports.paidNothing"),
              row.cumulative_drift > 0 && t("home.lateTotal", { count: row.cumulative_drift }),
              row.status === "inactive" && t("student.leftTitle"),
            ]}
            right={
              Number(row.outstanding) > 0 ? (
                <span className="shrink-0 whitespace-nowrap rounded-full bg-bad-soft px-3 py-1 text-sm font-bold text-bad">
                  {formatMoney(row.outstanding)}
                </span>
              ) : (
                <span className="shrink-0 whitespace-nowrap rounded-full bg-ok-soft px-3 py-1 text-sm font-bold text-ok">
                  {t("owed.paidUp")}
                </span>
              )
            }
          />
        ))}
      </StudentRows>
    </section>
  );
}
