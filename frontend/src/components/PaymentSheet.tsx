import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { listStudents } from "../api/endpoints";
import type { StudentListItem } from "../api/types";
import { useApi } from "../lib/useApi";
import { useDebounced } from "../lib/useDebounced";
import { formatMoney } from "../lib/money";
import { PaymentSheetContext } from "../lib/paymentSheetContext";
import { AsyncView, Modal } from "./ui";
import { Avatar, OwedPill } from "./people";
import { CheckIcon, SearchIcon } from "./icons";
import { RecordPaymentForm } from "./students/RecordPaymentForm";

type Sheet = { open: false } | { open: true; studentId?: number; month?: string; pickedHere: boolean };

/**
 * Taking a payment is the app's most frequent job, so it is one sheet reachable from anywhere:
 * the Accueil button, a student's page, the side menu on a computer. Started without a student,
 * it asks who first, with the students who owe at the top.
 */
export function PaymentSheetProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [sheet, setSheet] = useState<Sheet>({ open: false });
  const [version, setVersion] = useState(0);
  const [toast, setToast] = useState<string | null>(null);

  const open = useCallback(
    (studentId?: number, month?: string) =>
      setSheet({ open: true, studentId, month, pickedHere: studentId === undefined }),
    [],
  );
  const close = useCallback(() => setSheet({ open: false }), []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  const value = useMemo(() => ({ open, version }), [open, version]);

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
              onSuccess={(amount, name) => {
                close();
                setVersion((v) => v + 1);
                setToast(t("pay.done", { amount: formatMoney(amount), name }));
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
          <p className="flex items-center gap-2 rounded-2xl bg-ink px-4 py-3 font-bold text-ground shadow-xl">
            <CheckIcon className="h-5 w-5 text-ok" />
            {toast}
          </p>
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
      <AsyncView state={state} onRetry={state.reload} isEmpty={(rows) => rows.length === 0} emptyMessage={t("students.empty")}>
        {(rows) => (
          <ul className="-mx-2 flex flex-col">
            {owingFirst(rows).map((s) => (
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
                  <OwedPill monthsOverdue={s.months_overdue} amountOwed={s.amount_owed} monthlyPrice={s.monthly_price} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </div>
  );
}

/** Students who owe first, most months first; then everyone else by name. */
function owingFirst(rows: StudentListItem[]): StudentListItem[] {
  return [...rows].sort(
    (a, b) => b.months_overdue - a.months_overdue || a.full_name.localeCompare(b.full_name),
  );
}
