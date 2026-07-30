/** Shared input styling for all form fields; error state tints the border rose. */
export function inputClass(error?: boolean): string {
  return `w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-1 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 ${
    error
      ? "border-rose-400 focus:border-rose-500 focus:ring-rose-500 dark:border-rose-500"
      : "border-slate-300 focus:border-indigo-500 focus:ring-indigo-500 dark:border-slate-600 dark:focus:border-indigo-400 dark:focus:ring-indigo-400"
  }`;
}
