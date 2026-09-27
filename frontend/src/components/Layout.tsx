import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { SignOutButton } from "./SignOutButton";

/**
 * Destinations only, in the order the work happens: who you teach, what you charge, what came in,
 * what's still owed.
 *
 * "Enrol a student" used to sit here, between Packs and Reports. It is an *action*, not a place,
 * and it now lives as the primary button on the students page — which is where you already are
 * when you need it. The two report pages collapsed into one entry with tabs inside, for the same
 * reason a nav bar shouldn't enumerate a page's sub-views.
 */
const navItems = [
  { to: "/", key: "dashboard", end: true },
  { to: "/students", key: "students", end: false },
  { to: "/classes", key: "classes", end: false },
  { to: "/packs", key: "packs", end: false },
  { to: "/reports", key: "report", end: false },
  { to: "/debts", key: "debts", end: false },
] as const;

export function Layout() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        {/* Two rows on a phone, one from `sm` up. Wrapping six nav items into three lines ate a
            third of a 375px viewport before anything useful appeared. */}
        <div className="mx-auto max-w-5xl px-4 py-3 sm:flex sm:items-center sm:justify-between sm:gap-3 sm:px-6 sm:py-4">
          <div className="flex items-center justify-between gap-3">
            <span className="font-semibold text-slate-900 dark:text-slate-100">
              {t("app.title")}
            </span>
            {/* Theme and language sit on the title row on a phone, where the nav row is already
                full, and rejoin the nav on wider screens. */}
            <span className="flex items-center gap-2 sm:hidden">
              <ThemeToggle />
              <LanguageSwitcher />
              <SignOutButton />
            </span>
          </div>
          {/* Scrolls sideways rather than wrapping: one predictable row, and the active item is
              always where you left it. `-mx-4 px-4` lets it bleed to the screen edge. */}
          <nav className="-mx-4 mt-2 flex items-center gap-1 overflow-x-auto px-4 pb-1 sm:mx-0 sm:mt-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `shrink-0 rounded-md px-3 py-2 text-sm font-medium ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`
                }
              >
                {t(`nav.${item.key}`)}
              </NavLink>
            ))}
            <span className="ml-2 hidden sm:inline-flex">
              <ThemeToggle />
            </span>
            <span className="ml-2 hidden sm:inline-flex">
              <LanguageSwitcher />
            </span>
            <span className="ml-2 hidden sm:inline-flex">
              <SignOutButton />
            </span>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
