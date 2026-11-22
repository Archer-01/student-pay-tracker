import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { deletePayment, listStudents } from "../api/endpoints";
import type { StudentListItem } from "../api/types";
import { useApi } from "../lib/useApi";
import { useDebounced } from "../lib/useDebounced";
import { formatMoney } from "../lib/money";
import { PaymentSheetContext } from "../lib/paymentSheetContext";
import { connectivity, useReadOnly } from "../lib/connectivity";
import { resolveErrorMessage } from "../lib/errors";
import { AsyncView, Modal } from "./ui";
import { Avatar, OwedPill } from "./people";
import { SearchIcon } from "./icons";
import { RecordPaymentForm } from "./students/RecordPaymentForm";

type Sheet = { open: false } | { open: true; studentId?: number; month?: string; pickedHere: boolean };

type Toast = {
  /** New for every message, so one replacing another slides in rather than just swapping text. */
  id: number;
  message: string;
  /** An error is said plainly, without the check mark. */
  failed?: boolean;
  /** The payment just recorded, while it can still be taken back. */
  undo?: { studentId: number; cycleNumber: number };
  /** The undo is on its way: the message stays until the server has answered. */
  undoing?: boolean;
  leaving: boolean;
};

/**
 * Taking a payment is the app's most frequent job, so it is one sheet reachable from anywhere:
 * the Accueil button, a student's page, the side menu on a computer. Started without a student,
 * it asks who first, with the students who owe at the top.
 */
export function PaymentSheetProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [sheet, setSheet] = useState<Sheet>({ open: false });
  const [version, setVersion] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastId = useRef(0);
  const readOnly = useReadOnly();

  const show = useCallback((next: Omit<Toast, "id" | "leaving">) => {
    toastId.current += 1;
    setToast({ ...next, id: toastId.current, leaving: false });
  }, []);

  const open = useCallback(
    (studentId?: number, month?: string) => {
      // Read only offline: a payment couldn't be saved, so don't let one be typed in.
      if (connectivity().mode !== "live") return;
      setSheet({ open: true, studentId, month, pickedHere: studentId === undefined });
    },
    [],
  );
  const close = useCallback(() => setSheet({ open: false }), []);
  const announce = useCallback(
    (message: string, undo?: Toast["undo"]) => {
      setVersion((v) => v + 1);
      show({ message, undo });
    },
    [show],
  );
  const changed = useCallback((message: string) => announce(message), [announce]);

  // A payment taken by mistake (wrong student, wrong month) is taken back from its confirmation,
  // rather than by finding the month on the student's page.
  const undo = useCallback(
    async ({ studentId, cycleNumber }: NonNullable<Toast["undo"]>) => {
      if (connectivity().mode !== "live") return;
      setToast((current) => current && { ...current, undoing: true, leaving: false });
      try {
        await deletePayment(studentId, cycleNumber);
        changed(t("pay.undone"));
      } catch (err) {
        // Nothing changed, so nothing to refresh: just say why.
        show({ message: resolveErrorMessage(err, t), failed: true });
      }
    },
    [changed, show, t],
  );

  useEffect(() => {
    if (!toast || toast.undoing) return;
    // Fade out for the last 200ms rather than vanishing. A second longer with an undo on offer:
    // time to read the message and still reach the button.
    const timer = toast.leaving
      ? setTimeout(() => setToast(null), 200)
      : setTimeout(() => setToast({ ...toast, leaving: true }), toast.undo ? 5800 : 4800);
    return () => clearTimeout(timer);
  }, [toast]);

  const value = useMemo(() => ({ open, version, changed }), [open, version, changed]);

  return (
    <PaymentSheetContext.Provider value={value}>
      {children}
      {sheet.open && (
        <Modal title={t("pay.title")} onClose={close}>
          {sheet.studentId === undefined ? (
            <StudentPicker onPick={(id) => setSheet({ open: true, studentId: id, pickedHere: true })} />
          ) : (
            <RecordPaymentForm
              studentId={sheet.studentId}
              initialMonth={sheet.month}
              onCancel={close}
              onChangeStudent={sheet.pickedHere ? () => setSheet({ open: true, pickedHere: true }) : undefined}
              onSuccess={(amount, name, cycleNumber) => {
                const studentId = sheet.studentId!;
                close();
                announce(t("pay.done", { amount: formatMoney(amount), name }), { studentId, cycleNumber });
              }}
            />
          )}
        </Modal>
      )}
      {/* Above the tab bar on a phone; bottom corner on a computer. */}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-50 flex justify-center lg:inset-x-auto lg:bottom-6 lg:right-6"
      >
        {toast && (
          <div
            key={toast.id}
            className={`flex items-center gap-2 rounded-2xl bg-ink px-4 py-3 font-bold text-ground shadow-xl ${
              toast.leaving ? "animate-toast-out" : "animate-toast-in"
            }`}
          >
            {!toast.failed && <DrawnCheck />}
            <p>{toast.message}</p>
            {/* Taking a payment back is a write, so not while read only. The container lets taps
                through to the page beneath; only the button catches them. */}
            {toast.undo && !readOnly && (
              <button
                type="button"
                onClick={() => undo(toast.undo!)}
                disabled={toast.undoing}
                className="pointer-events-auto -my-2 -mr-2 min-h-11 shrink-0 rounded-xl px-3 font-bold text-ground underline underline-offset-4 transition active:scale-[0.97] disabled:opacity-50"
              >
                {t("pay.undo")}
              </button>
            )}
          </div>
        )}
      </div>
    </PaymentSheetContext.Provider>
  );
}

function StudentPicker({ onPick }: { onPick: (id: number) => void }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), 250);
  const state = useApi(() => listStudents({ status: "active", q: q || undefined }), [q]);
  const onlyFree = state.status === "success" && payableFirst(state.data).length === 0 ? state.data.length : 0;

  return (
    <div className="flex flex-col gap-4">
      <label className="flex min-h-12 items-center gap-2 rounded-xl border-2 border-line bg-surface px-3 focus-within:border-brand">
        <SearchIcon className="h-5 w-5 text-muted" />
        <span className="sr-only">{t("pay.pickStudent")}</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("pay.searchStudent")}
          className="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-placeholder"
        />
      </label>
      <AsyncView
        state={state}
        onRetry={state.reload}
        // Empty once the free students are left out; if they were all there was, say so.
        isEmpty={(rows) => payableFirst(rows).length === 0}
        emptyMessage={onlyFree ? t("pay.onlyFree", { count: onlyFree }) : t("students.empty")}
      >
        {(rows) => (
          <ul className="-mx-2 flex flex-col">
            {payableFirst(rows).map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onPick(s.id)}
                  className="flex min-h-14 w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-ground"
                >
                  <Avatar name={s.full_name} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-bold">{s.full_name}</span>
                    {s.school_class && (
                      <span className="block truncate text-sm text-muted">
                        {s.school_class.level} {s.school_class.name}
                      </span>
                    )}
                  </span>
                  <OwedPill monthsOverdue={s.months_overdue} amountOwed={s.amount_owed} priceStatus={s.price_status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </div>
  );
}

/**
 * Who can be sent a payment: students who owe first, most months first, then everyone else by
 * name. A student free on purpose can't be (decision 0014).
 */
function payableFirst(rows: StudentListItem[]): StudentListItem[] {
  return rows.filter((s) => s.price_status !== "free").sort(
    (a, b) => b.months_overdue - a.months_overdue || a.full_name.localeCompare(b.full_name),
  );
}

/** The payment's confirmation: a check mark that draws itself once the message has arrived. */
function DrawnCheck() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0 text-ok" fill="none" aria-hidden="true">
      <path
        d="M5 12.5l4.5 4.5L19 7.5"
        stroke="currentColor"
        strokeWidth={2.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={24}
        className="animate-draw"
      />
    </svg>
  );
}
