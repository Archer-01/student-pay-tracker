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
