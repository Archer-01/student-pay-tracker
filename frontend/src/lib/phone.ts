/**
 * WhatsApp wants a phone number in international form, digits only ("212612345678"). The app
 * stores numbers as typed, which for these teachers is almost always the Moroccan local form
 * ("06 12 34 56 78"), so local numbers get Morocco's 212 and lose their leading 0. A number
 * written with its own country code ("+33 6…", "0033 6…") is kept as is.
 *
 * Returns `null` rather than guessing when the number doesn't look like one.
 */
export function whatsappNumber(phone: string): string | null {
  const trimmed = phone.trim();
  const international = trimmed.startsWith("+") || trimmed.startsWith("00");
  // "+212 (0)6…" is a common way of writing the same number; the "(0)" is not dialled.
  let digits = trimmed.replace(/\(0\)/g, "").replace(/\D/g, "");
  if (international) {
    if (trimmed.startsWith("00")) digits = digits.slice(2);
    return digits.length >= 8 && digits.length <= 15 ? digits : null;
  }
  if (digits.startsWith("212") && digits.length === 12) return digits;
  if (digits.startsWith("0") && digits.length === 10) return `212${digits.slice(1)}`;
  if (digits.length === 9 && /^[5-7]/.test(digits)) return `212${digits}`;
  return null;
}

/** A link that opens a WhatsApp chat with this number, or `null` if the number can't be read. */
export function whatsappLink(phone: string): string | null {
  const number = whatsappNumber(phone);
  return number ? `https://wa.me/${number}` : null;
}
