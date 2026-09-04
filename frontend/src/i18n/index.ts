import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

export const SUPPORTED_LOCALES = ["en", "fr"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const STORAGE_KEY = "ardoise.locale";

/**
 * `localStorage` read/write that survives not having one.
 *
 * This module touches storage at import time, and it is imported by `client.ts` — so anything
 * that loads the API layer outside a browser tab loads this too. Node 22+ exposes a `localStorage`
 * global that is `undefined` unless the process was started with `--localstorage-file`, which
 * shadows any polyfill and makes the naive call throw on import. Private-mode browsers can also
 * throw on write. Losing the remembered locale is a shrug; failing to load is not.
 */
const storage = {
  get(key: string): string | null {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      // Nothing to do: the preference simply won't persist.
    }
  },
};

function initialLocale(): Locale {
  const stored = storage.get(STORAGE_KEY);
  if (stored === "en" || stored === "fr") return stored;
  return navigator?.language?.toLowerCase().startsWith("fr") ? "fr" : "en";
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
  storage.set(STORAGE_KEY, lng);
}
syncLocale(i18n.language);
i18n.on("languageChanged", syncLocale);

export default i18n;
