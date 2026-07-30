import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getDashboardSummary } from "../api/endpoints";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate } from "../lib/dates";
import { DriftBadge } from "../components/DriftBadge";
import { AsyncView, Card, PageHeader } from "../components/ui";

export function Dashboard() {
  const { t } = useTranslation();

  // Show all latecomers: 100 is the backend's max top-N and covers the whole roster (~20–30 students).
  const state = useApi(() => getDashboardSummary({ limit: 100 }), []);

  return (
    <div>
      <PageHeader title={t("pages.dashboard")} />

      <AsyncView state={state} onRetry={state.reload}>
        {(data) => (
          <>
            <p className="-mt-4 mb-6 text-sm text-slate-400 dark:text-slate-500">
              {t("dashboard.asOf", { date: formatDate(data.as_of) })}
            </p>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <StatTile label={t("dashboard.collectedThisMonth")}>
                {formatMoney(data.total_collected_this_month)}
              </StatTile>
              <StatTile label={t("dashboard.totalOutstanding")}>
                {formatMoney(data.total_outstanding)}
              </StatTile>
            </div>

            <Card padded={false}>
              <div className="border-b border-slate-200 px-5 py-3 dark:border-slate-800">
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {t("dashboard.topLatecomers")}
                </h2>
              </div>
              {data.top_latecomers.length === 0 ? (
                <p className="px-5 py-6 text-center text-sm text-slate-500 dark:text-slate-400">
                  {t("dashboard.empty")}
                </p>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.top_latecomers.map((s) => (
                    <li key={s.student_id} className="flex items-center justify-between px-5 py-3">
                      <Link
                        to={`/students/${s.student_id}`}
                        className="text-sm font-medium text-slate-900 hover:underline dark:text-slate-100"
                      >
                        {s.name}
                      </Link>
                      <DriftBadge drift={s.cumulative_drift} />
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

function StatTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Card>
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">{children}</p>
    </Card>
  );
}
