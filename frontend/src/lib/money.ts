import i18n from "../i18n";

/**
 * Money arrives as decimal strings (e.g. "300.00") — render as-is, never parse to a JS float for
 * math. `Number()` here only feeds `Intl` for display.
 *
 * Fees are whole dirhams, so cents appear only when there are some ("240 DH", "240,50 DH"), and
 * the currency is always named unless the caller says the sentence already does.
 */
export function formatMoney(value: string, { currency = true }: { currency?: boolean } = {}): string {
  const cents = /\.(\d+)/.exec(value)?.[1] ?? "";
  const hasCents = /[1-9]/.test(cents);
  const number = new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: hasCents ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(Number(value));
  return currency ? `${number}\u00a0DH` : number;
}
