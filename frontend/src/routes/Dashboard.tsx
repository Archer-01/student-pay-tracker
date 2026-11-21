import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getDashboardSummary } from "../api/endpoints";
import type { DashboardSummary } from "../api/types";
import { useApi } from "../lib/useApi";
import { usePaymentSheet } from "../lib/paymentSheetContext";
import { useReadOnly } from "../lib/connectivity";
import { formatMoney } from "../lib/money";
import { formatDate, formatMonthTitle, formatWeekday } from "../lib/dates";
import { AsyncView, Button } from "../components/ui";
import { OwedPill } from "../components/people";
import { StudentRow, StudentRows } from "../components/StudentRow";
import { useMoneyFacts } from "../lib/useMoneyFacts";
import { CheckIcon, ChevronRightIcon, PlusIcon } from "../components/icons";
import { Figure } from "../components/report";

/**
 * Accueil: this month's money, one button to take a payment, then who to chase, worst first.
 * Each row is one line (who, how late, what they owe) and opens the student.
 *
 * Former students who left owing get a quiet link to Bilan rather than a tile of their own: they
 * are worth knowing about, not worth the top of the screen every morning.
 */
export function Dashboard() {
  const { t } = useTranslation();
  const payments = usePaymentSheet();
  const readOnly = useReadOnly();
  const moneyFacts = useMoneyFacts();
  const state = useApi(() => getDashboardSummary({ limit: 100 }), [payments.version]);

  return (
    <AsyncView state={state} onRetry={state.reload}>
      {(data) => (
        <div className="flex flex-col gap-6">
          <h1 className="font-display text-3xl font-extrabold tracking-tight">
            {formatMonthTitle(data.as_of.slice(0, 7))}
          </h1>

          <section className="grid grid-cols-2 gap-3">
            <Figure
              label={t("home.collected")}
              value={formatMoney(data.total_collected_this_month)}
              hint={
                Number(data.share_this_month.percent) > 0
                  ? t("share.yoursOf", { amount: formatMoney(data.share_this_month.teacher) })
                  : undefined
              }
            />
            <Figure
              label={t("home.outstanding", { date: formatDate(data.as_of) })}
              value={formatMoney(data.total_outstanding)}
              alarming={Number(data.total_outstanding) > 0}
            />
          </section>

          <MonthFees progress={data.this_month} />

          {/* The side menu carries this button on a computer. */}
          <Button onClick={() => payments.open()} disabled={readOnly} className="min-h-14 w-full text-lg lg:hidden">
            <PlusIcon className="h-5 w-5" />
            {t("home.pay")}
          </Button>

          <Attention data={data} />

          <section className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-bold">
                {t("home.chase")}
              </h2>
              {data.top_debtors.length > 0 && (
                <span className="text-sm text-muted">{t("home.chaseOrder")}</span>
              )}
            </div>
            {data.top_debtors.length === 0 ? (
              <p className="flex items-center gap-2 rounded-2xl bg-ok-soft p-4 font-bold text-ok">
                <CheckIcon className="h-5 w-5" />
                {t("home.allPaid")}
              </p>
            ) : (
              <StudentRows label={t("home.chase")}>
                {data.top_debtors.map((d) => (
                  <StudentRow
                    key={d.student_id}
                    to={`/students/${d.student_id}`}
                    name={d.name}
                    facts={[
                      ...moneyFacts({ monthsOverdue: d.months_overdue, drift: d.cumulative_drift }),
                      d.class_label,
                    ]}
                    right={
                      <OwedPill monthsOverdue={d.months_overdue} amountOwed={d.amount_owed} monthlyPrice={d.monthly_price} />
                    }
                  />
                ))}
              </StudentRows>
            )}
          </section>

          <DueThisWeek rows={data.due_this_week} asOf={data.as_of} />

          {data.leavers_with_debt > 0 && (
            <Link
              to="/reports/leavers"
              className="flex min-h-14 items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3 hover:bg-ground"
            >
              <span className="flex-1">
                <span className="block font-bold">{t("home.leavers")}</span>
                <span className="block text-sm text-muted">
                  {t("home.leaversCount", { count: data.leavers_with_debt })}
                </span>
              </span>
              <span className="rounded-full bg-bad-soft px-3 py-1 text-sm font-bold text-bad">
                {formatMoney(data.owed_by_leavers)}
              </span>
              <ChevronRightIcon className="h-5 w-5 text-muted" />
            </Link>
          )}
        </div>
      )}
    </AsyncView>
  );
}

/**
 * This month's fees against what has been paid toward them: not the cash figure above, which
 * counts every payment received this month, back payments included. Hidden in a month where
 * nobody is due.
 */
function MonthFees({ progress }: { progress: DashboardSummary["this_month"] }) {
  const { t } = useTranslation();
  if (progress.students_expected === 0) return null;
  // Number() only draws the bar; the amounts shown stay the strings the server sent.
  const percent = Math.min(100, Math.round((Number(progress.settled) / Number(progress.expected)) * 100));
  const label = t("home.monthFees");
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4">
      <h2 className="text-sm text-muted">{label}</h2>
      <p className="font-display text-xl font-extrabold tracking-tight">
        {t("home.monthSettled", { count: progress.students_settled, total: progress.students_expected })}
      </p>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2.5 overflow-hidden rounded-full bg-line"
      >
        <div className="h-full rounded-full bg-brand" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-sm text-muted">
        {t("home.monthAmounts", { settled: formatMoney(progress.settled), expected: formatMoney(progress.expected) })}
      </p>
    </section>
  );
}

/** Who falls due in the next seven days and hasn't paid yet, soonest first. */
function DueThisWeek({ rows, asOf }: { rows: DashboardSummary["due_this_week"]; asOf: string }) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;
  const tomorrow = nextDay(asOf);
  const when = (due: string) =>
    due === asOf
      ? t("home.dueToday")
      : due === tomorrow
        ? t("home.dueTomorrow")
        : t("home.dueOn", { day: formatWeekday(due) });
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold">{t("home.week")}</h2>
        <span className="text-sm text-muted">{t("home.weekHint")}</span>
      </div>
      <StudentRows label={t("home.week")}>
        {rows.map((d) => (
          <StudentRow
            key={`${d.student_id}-${d.due_date}`}
            to={`/students/${d.student_id}`}
            name={d.name}
            facts={[when(d.due_date), d.class_label]}
            right={
              <span className="whitespace-nowrap rounded-full bg-brand-soft px-3 py-1 text-sm font-bold text-brand">
                {formatMoney(d.amount)}
              </span>
            }
          />
        ))}
      </StudentRows>
    </section>
  );
}

/** "2026-11-30" → "2026-12-01", by the calendar, not by adding milliseconds. */
function nextDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Data problems that quietly cost money, each with the button that fixes it. Hidden entirely
 * when there is nothing to fix, so its appearance means something.
 */
function Attention({ data }: { data: DashboardSummary }) {
  const { t } = useTranslation();
  const items = [
    ...data.unbilled_students.map((s) => ({
      id: s.student_id,
      text: t("home.noPrice", { name: s.name }),
      action: t("home.choosePack"),
    })),
    ...data.missing_leave_date.map((s) => ({
      id: s.student_id,
      text: t("home.leftNoDate", { name: s.name }),
      action: t("home.fix"),
    })),
  ];
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-warn-soft p-4 text-warn">
      <h2 className="font-bold">{t("home.attention")}</h2>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={`${item.id}-${item.action}`} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
            <span className="text-ink">{item.text}</span>
            <Link to={`/students/${item.id}`} className="min-h-11 content-center font-bold underline">
              {item.action}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
