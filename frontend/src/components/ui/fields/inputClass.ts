/** Shared input styling for all form fields: tall enough for a thumb, with a red border on error. */
export function inputClass(error?: boolean): string {
  return `min-h-12 w-full rounded-xl border-2 bg-surface px-3 py-2 text-base text-ink placeholder:text-placeholder focus:outline-none ${
    error ? "border-bad" : "border-line focus:border-brand"
  }`;
}
