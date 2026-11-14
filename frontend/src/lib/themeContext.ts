import { createContext, useContext } from "react";

/** What the teacher chose. "system" follows the phone, and is the default. */
export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "ardoise.theme";

export type ThemeContextValue = {
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
};

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
