import { useContext } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getDashboardSummary } from "../api/endpoints";
import type { DashboardSummary } from "../api/types";
import { useApi } from "../lib/useApi";
import { AuthContext } from "../lib/authContext";
import { usePaymentSheet } from "../lib/paymentSheetContext";
import { formatMoney } from "../lib/money";
import { formatDate, formatMonthTitle } from "../lib/dates";
import { AsyncView, Button } from "../components/ui";
import { Avatar, OwedPill } from "../components/people";
import { CheckIcon, ChevronRightIcon, PlusIcon } from "../components/icons";

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
  // Read without `useAuth` so the screen renders in isolation (tests); signed out never gets here.
  const user = useContext(AuthContext)?.user;
  const state = useApi(() => getDashboardSummary({ limit: 100 }), [payments.version]);

  return (
    <AsyncView state={state} onRetry={state.reload}>
      {(data) => (
        <div className="flex flex-col gap-6">
          <header>
            {user && <p className="text-muted">{t("home.greeting", { name: user.display_name })}</p>}
            <h1 className="font-display text-3xl font-extrabold tracking-tight">
              {formatMonthTitle(data.as_of.slice(0, 7))}
            </h1>
          </header>

          <section className="grid grid-cols-2 gap-3">
            <Figure label={t("home.collected")} value={formatMoney(data.total_collected_this_month)} />
            <Figure
              label={t("home.outstanding", { date: formatDate(data.as_of) })}
              value={formatMoney(data.total_outstanding)}
              alarming={Number(data.total_outstanding) > 0}
            />
          </section>

          {/* The side menu carries this button on a computer. */}
          <Button onClick={() => payments.open()} className="min-h-14 w-full text-lg lg:hidden">
            <PlusIcon className="h-5 w-5" />
            {t("home.pay")}
          </Button>

          <Attention data={data} />

          <section className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <h2 id="chase-heading" className="text-lg font-bold">
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
              <ul
                aria-labelledby="chase-heading"
                className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface"
              >
                {data.top_debtors.map((d) => (
                  <li key={d.student_id}>
                    <Link
                      to={`/students/${d.student_id}`}
                      className="flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-ground"
                    >
                      <Avatar name={d.name} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-bold">{d.name}</span>
                        <span className="block truncate text-sm text-muted">
                          {[
                            t("owed.monthsUnpaid", { count: d.months_overdue }),
                            d.cumulative_drift > 0 ? t("home.lateTotal", { count: d.cumulative_drift }) : null,
                            d.class_label,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      <OwedPill
                        monthsOverdue={d.months_overdue}
                        amountOwed={d.amount_owed}
                        monthlyPrice={d.monthly_price}
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

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

function Figure({ label, value, alarming = false }: { label: string; value: string; alarming?: boolean }) {
  return (
    <div className="flex flex-col justify-between gap-1 rounded-2xl border border-line bg-surface p-4">
      <span className="text-sm text-muted">{label}</span>
      <span
        className={`font-display text-2xl font-extrabold tabular-nums tracking-tight sm:text-3xl ${
          alarming ? "text-bad" : "text-ink"
        }`}
      >
        {value}
      </span>
    </div>
  );
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
