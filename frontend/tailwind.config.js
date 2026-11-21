/** @type {import('tailwindcss').Config} */

/*
 * The palette is the app's identity: "ardoise" is slate, so the brand is a deep slate green on a
 * chalk-white ground.
 *
 * Colours come from the semantic tokens below (`brand`, `ground`, `surface`, `ink`, `muted`,
 * `line`, and the status pairs `ok`, `warn`, `bad`, `off`), defined for light and dark in
 * `src/index.css`. Tailwind's own scales (`slate`, `indigo`…) are left at their defaults and
 * unused: one appearing in a diff is a colour that won't follow the theme.
 *
 * The semantic colours are CSS variables, so Tailwind's opacity shorthand (`bg-brand/35`) does
 * not work on them: it silently produces no colour at all. Add a solid token instead.
 */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "var(--brand)", soft: "var(--brand-soft)", mid: "var(--brand-mid)", ink: "var(--brand-ink)" },
        ok: { DEFAULT: "var(--ok)", soft: "var(--ok-soft)" },
        warn: { DEFAULT: "var(--warn)", soft: "var(--warn-soft)" },
        bad: { DEFAULT: "var(--bad)", soft: "var(--bad-soft)" },
        off: { DEFAULT: "var(--off)", soft: "var(--off-soft)" },
        school: "var(--school)",
        surface: "var(--surface)",
        ground: "var(--ground)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        placeholder: "var(--placeholder)",
      },
      /*
       * A handful of short entrances, each answering "where did this come from?" or "did that
       * work?". Nothing loops, nothing runs longer than a quarter of a second (the check mark
       * waits for the toast first), and all of it is switched off under "reduce motion" in
       * index.css.
       */
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "sheet-up": { from: { transform: "translateY(100%)" }, to: { transform: "translateY(0)" } },
        "dialog-in": {
          from: { opacity: "0", transform: "translateY(8px) scale(0.98)" },
          to: { opacity: "1", transform: "none" },
        },
        "toast-in": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "none" },
        },
        "toast-out": { from: { opacity: "1" }, to: { opacity: "0", transform: "translateY(6px)" } },
        draw: { from: { strokeDashoffset: "24" }, to: { strokeDashoffset: "0" } },
        "paid-pop": {
          "0%": { transform: "scale(1)" },
          "40%": { transform: "scale(1.08)" },
          "100%": { transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
        "sheet-up": "sheet-up 240ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "dialog-in": "dialog-in 180ms ease-out",
        "toast-in": "toast-in 220ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "toast-out": "toast-out 200ms ease-in forwards",
        draw: "draw 260ms ease-out 160ms both",
        "paid-pop": "paid-pop 320ms ease-out",
      },
      fontFamily: {
        sans: ['"Ardoise Digits"', '"Atkinson Hyperlegible"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        display: ['"Bricolage Grotesque Variable"', '"Atkinson Hyperlegible"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
