import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

/** Anything a user can tab to. Disabled and `tabindex="-1"` elements are deliberately excluded. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Lightweight modal: a sheet that rises from the bottom on a phone (where the thumb already is,
 * and the way phone apps present a quick task) and a centred panel from `sm` up. Closes on
 * backdrop click, the × button, or Escape.
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
  const { t } = useTranslation();
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
      className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto bg-black/45 sm:items-start sm:p-4 sm:pt-20"
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
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-2xl focus:outline-none sm:max-w-md sm:rounded-3xl sm:pb-0"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 bg-surface px-5 pb-2 pt-5">
          <h2 id={titleId} className="font-display text-xl font-extrabold tracking-tight text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ground text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
          >
            ✕
          </button>
        </div>
        <div ref={bodyRef} className="px-5 pb-6 pt-2">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
