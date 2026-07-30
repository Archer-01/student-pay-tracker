import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

export const SUPPORTED_LOCALES = ["en", "fr"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const STORAGE_KEY = "student-pay-tracker.locale";

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "fr") return stored;
  return navigator.language?.toLowerCase().startsWith("fr") ? "fr" : "en";
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    fr: { translation: fr },
  },
  lng: initialLocale(),
  fallbackLng: "en",
  supportedLngs: SUPPORTED_LOCALES,
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
});

// Keep <html lang> and the stored preference in sync with the active locale.
function syncLocale(lng: string) {
  document.documentElement.lang = lng;
  localStorage.setItem(STORAGE_KEY, lng);
}
syncLocale(i18n.language);
i18n.on("languageChanged", syncLocale);

export default i18n;
