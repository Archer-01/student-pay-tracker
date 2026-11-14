import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ThemeContext, THEME_STORAGE_KEY, type ThemePreference } from "./themeContext";

/** The page's background in each theme (`--ground`), which the phone's status bar takes on. */
const STATUS_BAR = { light: "#f3f6f5", dark: "#111615" } as const;

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
      // Installed as an app there is no browser chrome, so the status bar is the page's top edge:
      // it follows the theme actually showing, including an explicit choice in Réglages.
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", dark ? STATUS_BAR.dark : STATUS_BAR.light);
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
