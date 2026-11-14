import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/authContext";
import { useTheme, type ThemePreference } from "../lib/themeContext";
import { SUPPORTED_LOCALES, type Locale } from "../i18n";
import { ChevronRightIcon, SignOutIcon } from "../components/icons";
import { Avatar } from "../components/people";

/**
 * Everything set up once and rarely touched: classes, the price grid, language, appearance, and
 * signing out. Grouped the way a phone's own settings are, so it reads as familiar.
 */
export function Settings() {
  const { t, i18n } = useTranslation();
  const { user, signOut } = useAuth();
  const { preference, setPreference } = useTheme();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-3xl font-extrabold tracking-tight">{t("settings.title")}</h1>

      {user && (
        <section className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4">
          <Avatar name={user.display_name} />
          <span className="flex flex-col">
            <span className="font-bold">{user.display_name}</span>
            <span className="text-sm text-muted">{t("settings.signedIn")}</span>
          </span>
        </section>
      )}

      <Group label={t("settings.school")}>
        <LinkRow to="/settings/packs">{t("settings.prices")}</LinkRow>
        <LinkRow to="/settings/classes">{t("settings.classes")}</LinkRow>
      </Group>

      <Group label={t("settings.app")}>
        <div className="flex flex-col gap-3 p-4">
          <span className="font-bold" id="language-label">
            {t("language.label")}
          </span>
          <Segmented<Locale>
            labelledBy="language-label"
            value={i18n.language as Locale}
            onChange={(lng) => void i18n.changeLanguage(lng)}
            options={SUPPORTED_LOCALES.map((lng) => ({ value: lng, label: t(`settings.languages.${lng}`) }))}
          />
        </div>
        <div className="flex flex-col gap-3 p-4">
          <span className="font-bold" id="appearance-label">
            {t("settings.appearance")}
          </span>
          <Segmented<ThemePreference>
            labelledBy="appearance-label"
            value={preference}
            onChange={setPreference}
            options={(["system", "light", "dark"] as const).map((value) => ({
              value,
              label: t(`settings.themes.${value}`),
            }))}
          />
        </div>
      </Group>

      <button
        type="button"
        onClick={() => void signOut()}
        className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-line bg-surface font-bold text-bad hover:bg-bad-soft"
      >
        <SignOutIcon className="h-5 w-5" />
        {t("auth.signOut")}
      </button>
    </div>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="px-1 text-xs font-bold uppercase tracking-wider text-muted">{label}</h2>
      <div className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {children}
      </div>
    </section>
  );
}

function LinkRow({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="flex min-h-14 items-center justify-between gap-3 px-4 font-bold hover:bg-ground"
    >
      {children}
      <ChevronRightIcon className="h-5 w-5 text-muted" />
    </Link>
  );
}

/** A row of mutually exclusive choices, all visible at once: easier than a dropdown on a phone. */
function Segmented<T extends string>({
  value,
  onChange,
  options,
  labelledBy,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  labelledBy: string;
}) {
  return (
    <div role="radiogroup" aria-labelledby={labelledBy} className="grid auto-cols-fr grid-flow-col gap-1 rounded-xl bg-ground p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={`min-h-11 rounded-lg px-2 text-sm font-bold transition-colors ${
            value === option.value ? "bg-surface text-brand shadow-sm" : "text-muted"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
