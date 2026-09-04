import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getDashboardSummary } from "../api/endpoints";
import type { StudentDigest } from "../api/types";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate } from "../lib/dates";
import { DriftBadge } from "../components/DriftBadge";
import { AsyncView, Card, PageHeader } from "../components/ui";

/**
 * The landing page answers two questions, in this order: **who do I chase**, and **what is
 * quietly wrong**.
 *
 * It used to rank students by drift — cumulative days late. Drift is the metric this product is
 * built on and still sits on every row, but it is the wrong thing to sort a worklist by: someone
 * with 25 days of drift who is fully paid up needs nothing, while someone who has never paid at
 * all has no drift whatsoever and owes a fortune. Money leads; drift breaks ties.
 */
export function Dashboard() {
  const { t } = useTranslation();
  // 100 is the backend's max top-N and covers the whole roster (~20–30 students).
  const state = useApi(() => getDashboardSummary({ limit: 100 }), []);

  return (
    <div>
      <PageHeader title={t("pages.dashboard")} />

      <AsyncView state={state} onRetry={state.reload}>
        {(data) => (
          <>
            <p className="-mt-4 mb-6 text-sm text-slate-400 dark:text-slate-500">
              {t("dashboard.asOf", { date: formatDate(data.as_of) })} ·{" "}
              {t("dashboard.activeStudents", { count: data.active_students })}
            </p>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatTile label={t("dashboard.collectedThisMonth")}>
                {formatMoney(data.total_collected_this_month)}
              </StatTile>
              <StatTile label={t("dashboard.totalOutstanding")}>
                {formatMoney(data.total_outstanding)}
              </StatTile>
              {/* Kept apart from the figure above, which covers students still attending:
                  chasing someone who already left is a different conversation. Only rendered
                  when there is something to chase. */}
              {/* focus-visible rather than a bare outline-none: this tile is a link, and
                  removing the outline without replacing it hides it from keyboard users. */}
              {data.leavers_with_debt > 0 && (
                <Link
                  to="/debts"
                  className="block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
                >
                  <StatTile label={t("debts.onDashboard")} tone="alert">
                    {formatMoney(data.owed_by_leavers)}
                    <span className="ml-2 text-sm font-normal text-slate-400">
                      ({data.leavers_with_debt})
                    </span>
                  </StatTile>
                </Link>
              )}
            </div>

            {/* Problems that raise no error and produce no bill. Absent entirely when there are
                none, so a healthy database shows a clean page rather than a row of green ticks. */}
            <Attention
              unbilled={data.unbilled_students}
              missingLeaveDate={data.missing_leave_date}
            />

            <Card padded={false}>
              <div className="flex items-baseline justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {t("dashboard.whoToChase")}
                </h2>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {t("dashboard.rankedByOwed")}
                </span>
              </div>
              {data.top_debtors.length === 0 ? (
                <p className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                  {t("dashboard.empty")}
                </p>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.top_debtors.map((s) => (
                    <li
                      key={s.student_id}
                      className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/students/${s.student_id}`}
                          className="text-sm font-medium text-slate-900 hover:underline dark:text-slate-100"
                        >
                          {s.name}
                        </Link>
                        {s.class_label && (
                          <span className="ml-2 text-xs text-slate-400 dark:text-slate-500">
                            {s.class_label}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {t("dashboard.monthsBehind", { count: s.months_overdue })}
                      </span>
                      <DriftBadge drift={s.cumulative_drift} />
                      <span className="w-24 text-right text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                        {formatMoney(s.amount_owed)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        )}
      </AsyncView>
    </div>
  );
}

function Attention({
  unbilled,
  missingLeaveDate,
}: {
  unbilled: StudentDigest[];
  missingLeaveDate: StudentDigest[];
}) {
  const { t } = useTranslation();
  if (unbilled.length === 0 && missingLeaveDate.length === 0) return null;

  return (
    <Card tone="alert" className="mb-6">
      <h2 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
        {t("dashboard.attention")}
      </h2>
      <ul className="mt-2 space-y-1.5 text-sm text-amber-900 dark:text-amber-200">
        {unbilled.length > 0 && (
          <AttentionRow
            message={t("dashboard.unbilled", { count: unbilled.length })}
            students={unbilled}
          />
        )}
        {missingLeaveDate.length > 0 && (
          <AttentionRow
            message={t("dashboard.missingLeaveDate", { count: missingLeaveDate.length })}
            students={missingLeaveDate}
          />
        )}
      </ul>
    </Card>
  );
}

function AttentionRow({ message, students }: { message: string; students: StudentDigest[] }) {
  return (
    <li>
      {message}{" "}
      {students.map((s, i) => (
        <span key={s.student_id}>
          {i > 0 && ", "}
          <Link to={`/students/${s.student_id}`} className="underline underline-offset-2">
            {s.name}
          </Link>
        </span>
      ))}
    </li>
  );
}

function StatTile({
  label,
  children,
  tone = "normal",
}: {
  label: string;
  children: ReactNode;
  tone?: "normal" | "alert";
}) {
  return (
    <Card>
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          tone === "alert"
            ? "text-rose-700 dark:text-rose-400"
            : "text-slate-900 dark:text-slate-100"
        }`}
      >
        {children}
      </p>
    </Card>
  );
}
