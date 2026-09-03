import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

const tabs = [
  { to: "/reports/monthly", key: "report" },
  { to: "/reports/annual", key: "annual" },
] as const;

/** Month and year are two views of the same question, so they are tabs rather than nav entries. */
export function ReportTabs() {
  const { t } = useTranslation();
  return (
    <div className="mb-6 flex gap-1 border-b border-slate-200 dark:border-slate-800">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              isActive
                ? "border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300"
                : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            }`
          }
        >
          {t(`nav.${tab.key}`)}
        </NavLink>
      ))}
    </div>
  );
}
