import { useTranslation } from "react-i18next";
import { SUPPORTED_LOCALES } from "../i18n";

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  return (
    <div
      className="flex items-center gap-1 rounded-xl bg-surface p-1 ring-1 ring-line"
      aria-label={t("language.label")}
    >
      {SUPPORTED_LOCALES.map((lng) => (
        <button
          key={lng}
          onClick={() => i18n.changeLanguage(lng)}
          aria-pressed={i18n.language === lng}
          className={`min-h-11 min-w-11 rounded-lg px-3 text-sm font-bold uppercase ${
            i18n.language === lng ? "bg-brand text-brand-ink" : "text-muted hover:text-ink"
          }`}
        >
          {lng}
        </button>
      ))}
    </div>
  );
}
