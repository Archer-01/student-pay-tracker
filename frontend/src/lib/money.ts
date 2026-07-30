import i18n from "../i18n";

/** Money arrives as decimal strings (e.g. "300.00") — render as-is, never parse to a JS float for math. */
export function formatMoney(value: string): string {
  const n = Number(value);
  return new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}
