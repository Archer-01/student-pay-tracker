/** @type {import('tailwindcss').Config} */

/*
 * The palette is the app's identity: "ardoise" is slate, so the brand is a deep slate green on a
 * chalk-white ground.
 *
 * `indigo` and `slate` are *redefined* rather than added to. Every screen was written against
 * those two scales, so remapping them restyles the whole app at once; screens move to the
 * semantic tokens below (`brand`, `ok`, `warn`, `bad`, `off`) as they are rebuilt. A new screen
 * should use the semantic names, not `indigo`.
 *
 * The semantic colours are CSS variables, so Tailwind's opacity shorthand (`bg-brand/35`) does
 * not work on them: it silently produces no colour at all. Add a solid token instead.
 */
const slateGreen = {
  50: "#eef5f4",
  100: "#dceae8",
  200: "#b9d5d1",
  300: "#8db8b2",
  400: "#5e968f",
  500: "#3d7871",
  600: "#2a625c",
  700: "#1f4e4a",
  800: "#1a3f3c",
  900: "#163331",
  950: "#0c1d1c",
};

// Neutrals with a slight green bias toward the brand, so greys look chosen rather than default.
const chalk = {
  50: "#f3f6f5",
  100: "#e8edeb",
  200: "#dce3e1",
  300: "#c3cdca",
  400: "#94a19e",
  500: "#66736f",
  600: "#4d5956",
  700: "#384340",
  800: "#232c2a",
  900: "#19201f",
  950: "#111615",
};

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        indigo: slateGreen,
        slate: chalk,
        brand: { DEFAULT: "var(--brand)", soft: "var(--brand-soft)", mid: "var(--brand-mid)", ink: "var(--brand-ink)" },
        ok: { DEFAULT: "var(--ok)", soft: "var(--ok-soft)" },
        warn: { DEFAULT: "var(--warn)", soft: "var(--warn-soft)" },
        bad: { DEFAULT: "var(--bad)", soft: "var(--bad-soft)" },
        off: { DEFAULT: "var(--off)", soft: "var(--off-soft)" },
        surface: "var(--surface)",
        ground: "var(--ground)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        placeholder: "var(--placeholder)",
      },
      fontFamily: {
        sans: ['"Ardoise Digits"', '"Atkinson Hyperlegible"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        display: ['"Bricolage Grotesque Variable"', '"Atkinson Hyperlegible"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
