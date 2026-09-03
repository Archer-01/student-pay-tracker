import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";

const navItems = [
  { to: "/", key: "dashboard", end: true },
  { to: "/students", key: "students", end: false },
  { to: "/classes", key: "classes", end: false },
  { to: "/packs", key: "packs", end: false },
  { to: "/students/new", key: "enroll", end: false },
  { to: "/reports/monthly", key: "report", end: false },
  { to: "/reports/annual", key: "annual", end: false },
  { to: "/debts", key: "debts", end: false },
] as const;

export function Layout() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <span className="font-semibold text-slate-900 dark:text-slate-100">{t("app.title")}</span>
          <nav className="flex flex-wrap items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm font-medium ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`
                }
              >
                {t(`nav.${item.key}`)}
              </NavLink>
            ))}
            <span className="ml-2">
              <ThemeToggle />
            </span>
            <span className="ml-2">
              <LanguageSwitcher />
            </span>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
