import type { ComponentType, SVGProps } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/authContext";
import { usePaymentSheet } from "../lib/paymentSheetContext";
import { ChartIcon, HomeIcon, PlusIcon, SettingsIcon, StudentsIcon } from "./icons";
import { PaymentSheetProvider } from "./PaymentSheet";
import { Logo } from "./Logo";

/**
 * Four places, in the order the work happens: today, the students, the money, and the things set
 * up once a year. Classes, prices, language and sign-out live under Réglages rather than in the
 * bar, because a teacher touches them a few times a year, not a few times a day.
 *
 * On a phone the four sit at the bottom, under the thumb, and always fit: the old top bar was
 * 602px wide on a 390px screen and hid two of its six items. From `lg` up they become a side menu.
 */
const navItems: {
  to: string;
  key: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
}[] = [
  { to: "/", key: "home", icon: HomeIcon, end: true },
  { to: "/students", key: "students", icon: StudentsIcon },
  { to: "/reports", key: "reports", icon: ChartIcon },
  { to: "/settings", key: "settings", icon: SettingsIcon },
];

export function Layout() {
  return (
    <PaymentSheetProvider>
      <Shell />
    </PaymentSheetProvider>
  );
}

function Shell() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const payments = usePaymentSheet();

  return (
    // No full-height rule: `body` already paints the background, and `min-h-screen` (100vh) is
    // taller than a phone's visible area while the address bar shows, adding a scroll for nothing.
    <div className="lg:pl-64">
      <aside className="hidden border-r border-line bg-surface px-4 pb-6 pt-[calc(1.5rem+env(safe-area-inset-top))] lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:w-64 lg:flex-col">
        <span className="flex items-center gap-2.5 px-3 font-display text-2xl font-extrabold tracking-tight text-brand">
          <Logo />
          {t("app.title")}
        </span>
        <nav aria-label={t("nav.label")} className="mt-8 flex flex-col gap-1">
          {navItems.map(({ to, key, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-3 font-bold transition-colors ${
                  isActive ? "bg-brand-soft text-brand" : "text-muted hover:bg-ground hover:text-ink"
                }`
              }
            >
              <Icon className="h-5 w-5" />
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
        {/* On a computer the most frequent job sits in the menu itself, one click from any page. */}
        <button
          type="button"
          onClick={() => payments.open()}
          className="mt-6 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand px-4 font-bold text-brand-ink hover:opacity-90"
        >
          <PlusIcon className="h-5 w-5" />
          {t("nav.pay")}
        </button>
        {user && (
          <p className="mt-auto px-3 text-sm text-muted">
            {t("auth.signedInAs", { name: user.display_name })}
          </p>
        )}
      </aside>

      {/* Bottom padding clears the tab bar on a phone, safe-area inset included. */}
      <main className="mx-auto max-w-3xl px-4 pb-[calc(6rem+env(safe-area-inset-bottom))] pt-[calc(1.5rem+env(safe-area-inset-top))] sm:px-6 lg:max-w-4xl lg:px-10 lg:pb-12 lg:pt-[calc(2.5rem+env(safe-area-inset-top))]">
        <Outlet />
      </main>

      <nav
        aria-label={t("nav.label")}
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {navItems.map(({ to, key, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex min-h-16 flex-col items-center justify-center gap-1 text-xs font-bold ${
                isActive ? "text-brand" : "text-muted"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`flex h-8 w-14 items-center justify-center rounded-full ${
                    isActive ? "bg-brand-soft" : ""
                  }`}
                >
                  <Icon className="h-[22px] w-[22px]" />
                </span>
                {t(`nav.${key}`)}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
