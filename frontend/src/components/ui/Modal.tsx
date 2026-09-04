import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Anything a user can tab to. Disabled and `tabindex="-1"` elements are deliberately excluded. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Lightweight modal: backdrop overlay + centered panel. Closes on backdrop click, the × button,
 * or Escape.
 *
 * Focus is managed, because `aria-modal` is a promise to assistive technology that the rest of
 * the page is inert — and on its own it does nothing to make that true:
 *
 * - opening moves focus into the dialog, so a keyboard user isn't left behind the overlay;
 * - Tab and Shift+Tab wrap inside it rather than walking onto the page underneath;
 * - closing returns focus to whatever opened it, so the user keeps their place;
 * - the page behind is locked from scrolling while it is open.
 */
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // Escape closes. Kept in its own effect so it re-binds if `onClose` changes identity.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;

    // Prefer the first field over the × button: these dialogs are mostly forms, and landing on
    // "close" is a poor first stop. Falls back to the panel itself when there is nothing to fill in.
    const firstField = bodyRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    (firstField ?? dialogRef.current)?.focus();

    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = overflow;
      // The opener may have unmounted with the dialog (a row that was deleted, say).
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  function trapTab(e: React.KeyboardEvent) {
    if (e.key !== "Tab") return;
    // Re-queried on each press: dialog contents change as fields appear and disappear.
    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;

    if (e.shiftKey && (active === first || active === dialogRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-20 dark:bg-black/60"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={trapTab}
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white shadow-xl focus:outline-none dark:border-slate-700 dark:bg-slate-900"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h2 id={titleId} className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <div ref={bodyRef} className="p-5">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
