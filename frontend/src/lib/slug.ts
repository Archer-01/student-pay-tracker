/**
 * An ASCII, filename-safe slug of a name: accents folded (e.g. an accented "e" becomes "e"),
 * every run of non-alphanumerics collapsed to a single hyphen, lowercased. Returns "" for names
 * with no ASCII letters/digits (e.g. Arabic script), so callers can fall back to an id-only
 * filename. Mirrors the backend's `_slugify_name` so client- and server-built filenames agree.
 */
export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // strip combining diacritics left by NFKD
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}
