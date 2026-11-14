import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

const tabs = [
  { to: "/reports/monthly", key: "month" },
  { to: "/reports/annual", key: "year" },
  { to: "/reports/leavers", key: "leavers" },
] as const;

/**
 * Bilan's three views of the money: this month, the year, and former students who left owing.
 * They are tabs rather than places in the bottom bar, which has room for four and no more.
 */
export function ReportTabs() {
  const { t } = useTranslation();
  return (
    <div className="mb-6 flex gap-1 overflow-x-auto rounded-xl bg-surface p-1 ring-1 ring-line">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `min-h-11 flex-1 shrink-0 whitespace-nowrap rounded-lg px-3 py-2 text-center text-sm font-bold ${
              isActive ? "bg-brand text-brand-ink" : "text-muted hover:text-ink"
            }`
          }
        >
          {t(`reports.tabs.${tab.key}`)}
        </NavLink>
      ))}
    </div>
  );
}
