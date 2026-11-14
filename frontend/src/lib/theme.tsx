import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ThemeContext, THEME_STORAGE_KEY, type ThemePreference } from "./themeContext";

/** Storage can be missing or throw (private mode, Node in tests); the preference just won't stick. */
function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // fall through to the default
  }
  return "system";
}

function writePreference(preference: ThemePreference): void {
  try {
    if (preference === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // nothing to do
  }
}

/**
 * Owns light/dark. By default it follows the phone, live: switching the phone to dark mode at
 * night switches the app too. An explicit choice in Réglages overrides that.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = preference === "dark" || (preference === "system" && media.matches);
      document.documentElement.classList.toggle("dark", dark);
      document.documentElement.style.colorScheme = dark ? "dark" : "light";
    };
    apply();
    writePreference(preference);
    if (preference !== "system") return;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [preference]);

  const value = useMemo(() => ({ preference, setPreference }), [preference]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
