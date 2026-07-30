import { useTranslation } from "react-i18next";
import { SUPPORTED_LOCALES } from "../i18n";

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  return (
    <div
      className="flex items-center gap-0.5 rounded-md border border-slate-200 p-0.5 dark:border-slate-700"
      aria-label={t("language.label")}
    >
      {SUPPORTED_LOCALES.map((lng) => (
        <button
          key={lng}
          onClick={() => i18n.changeLanguage(lng)}
          aria-pressed={i18n.language === lng}
          className={`rounded px-2 py-1 text-xs font-medium uppercase ${
            i18n.language === lng
              ? "bg-indigo-600 text-white"
              : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          }`}
        >
          {lng}
        </button>
      ))}
    </div>
  );
}
