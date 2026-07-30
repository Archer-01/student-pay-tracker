import type { TFunction } from "i18next";
import i18n from "../i18n";
import { ApiError } from "../api/client";

/**
 * Resolve a user-facing error message following the project convention:
 *   1. If it's an `ApiError` with a `code` we have a catalog entry for → use `errors.<code>`.
 *   2. Otherwise use `ApiError.message` — the backend already localizes domain `detail`
 *      (via the `Accept-Language` the client sends), and validation errors flatten to a string.
 *   3. Fall back to a generic localized message for anything non-`ApiError`.
 */
export function resolveErrorMessage(err: unknown, t: TFunction): string {
  if (err instanceof ApiError) {
    if (err.code && i18n.exists(`errors.${err.code}`)) {
      return t(`errors.${err.code}`);
    }
    return err.message;
  }
  return t("errors.generic");
}

/**
 * Extract per-field messages from a 422 validation error, keyed by field name (`loc.at(-1)`), so a form
 * can surface them inline. Returns `{}` for anything that isn't an `ApiError` with an array `detail`.
 * Note: these `msg` strings are English (the backend leaves 422 messages unlocalized) — prefer localized
 * client-side validation for the common cases and treat these as a fallback.
 */
export function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !Array.isArray(err.detail)) return {};
  const out: Record<string, string> = {};
  for (const d of err.detail) {
    const field = d.loc.at(-1);
    if (field !== undefined && !(field in out)) out[String(field)] = d.msg;
  }
  return out;
}
