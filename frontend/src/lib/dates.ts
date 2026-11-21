import i18n from "../i18n";

/** Format a `YYYY-MM-DD` date string with the active locale. Returns the raw input if unparseable. */
export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(d);
}

/** Format a `YYYY-MM` month string as a localized month + year. Returns the raw input if unparseable. */
export function formatMonth(ym: string): string {
  const d = new Date(`${ym}-01T00:00:00`);
  if (Number.isNaN(d.getTime())) return ym;
  return new Intl.DateTimeFormat(i18n.language, { month: "long", year: "numeric" }).format(d);
}

/** "2026-11" → "Novembre 2026": `formatMonth`, capitalised to stand alone as a title or a choice. */
export function formatMonthTitle(ym: string): string {
  const text = formatMonth(ym);
  return text.charAt(0).toLocaleUpperCase(i18n.language) + text.slice(1);
}

/**
 * "2026-07" → "Juil" / "Jul": a chart's month label. Short enough for twelve under a phone-wide
 * chart, long enough that June and July (or March and May) don't both read "J" (or "M").
 * The locale's own abbreviation, minus its full stop.
 */
export function formatMonthShort(ym: string): string {
  const d = new Date(`${ym}-01T00:00:00`);
  if (Number.isNaN(d.getTime())) return ym;
  const text = new Intl.DateTimeFormat(i18n.language, { month: "short" }).format(d).replace(/\.$/, "");
  return text.charAt(0).toLocaleUpperCase(i18n.language) + text.slice(1);
}

/** Today as `YYYY-MM-DD` in the teacher's own timezone, comparable with a date input's value. */
export function todayIso(): string {
  return localIso(new Date());
}

/** The calendar day of `d` where the phone is, as `YYYY-MM-DD`. Not `toISOString()`, which is
 * UTC: in Morocco that is the previous day until 1 a.m. */
export function localIso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** "2026-11-18" → "mercredi 18 nov." / "Wednesday, Nov 18": a day this week, said as a day. */
export function formatWeekday(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(i18n.language, { weekday: "long", day: "numeric", month: "short" }).format(d);
}

/** "2026-11-03" → "3 nov." / "Nov 3": a recent day, where the year goes without saying. */
export function formatDayMonth(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(i18n.language, { day: "numeric", month: "short" }).format(d);
}
