import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listClasses, listStudents } from "../api/endpoints";
import type { StudentListItem } from "../api/types";
import { useApi, type AsyncState } from "../lib/useApi";
import { useDebounced } from "../lib/useDebounced";
import { usePaymentsVersion } from "../lib/paymentSheetContext";
import { useReadOnly } from "../lib/connectivity";
import { AsyncView } from "../components/ui";
import { OwedPill, PunctualityPill } from "../components/people";
import { StudentRow, StudentRows } from "../components/StudentRow";
import { useMoneyFacts } from "../lib/useMoneyFacts";
import { usePunctualityText } from "../lib/punctuality";
import { PlusIcon, SearchIcon } from "../components/icons";

/**
 * "all", "owing" and "punctuality" are current students; "left" is everyone who has left; a
 * number is a class.
 */
type Filter = "all" | "owing" | "punctuality" | "left" | number;

/**
 * Everyone, one line each, alphabetical so a name is where you expect it. A large search box and
 * two rows of chips replace the four crammed filters: "Impayés" is one tap, each class is one
 * tap, and former students sit behind "Anciens" so the default list is the current year. Every
 * chip shows on a phone; the first row says how many students there are and how many owe.
 */
export function StudentsList() {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 250);
  const moneyFacts = useMoneyFacts();
  const punctualityText = usePunctualityText();
  const readOnly = useReadOnly();

  // Refreshes after a payment taken from the shared sheet, wherever it was opened.
  const paymentsVersion = usePaymentsVersion();
  // The current students, fetched once whichever chip is picked: the chips count them, and a
  // class is filtered here rather than by the server so the counts stay put.
  const current = useApi(() => listStudents({ status: "active", q: q || undefined }), [q, paymentsVersion]);
  // Former students only once "Anciens" is picked. Until then this resolves to null, which reads
  // as still loading, so a first tap never flashes "no students" before the rows arrive.
  const showingLeft = filter === "left";
  const former = useApi(
    () => (showingLeft ? listStudents({ status: "inactive", q: q || undefined }) : Promise.resolve(null)),
    [showingLeft, q, paymentsVersion],
  );
  const state = showingLeft ? asLoaded(former) : current;
  // Class chips. A failure here must not blank the page; the chips simply don't appear.
  const classes = useApi(() => listClasses(), []);

  const counted = (key: "allCount" | "owingCount", plain: "all" | "owing") =>
    current.status === "success"
      ? t(`students.filters.${key}`, { count: shown(current.data, plain).length })
      : t(`students.filters.${plain}`);
  const firstRow: { value: Filter; label: string }[] = [
    { value: "all", label: counted("allCount", "all") },
    { value: "owing", label: counted("owingCount", "owing") },
    { value: "punctuality", label: t("students.filters.punctuality") },
  ];
  const secondRow: { value: Filter; label: string }[] = [
    ...(classes.data ?? []).map((c) => ({ value: c.id as Filter, label: `${c.level} ${c.name}` })),
    { value: "left", label: t("students.filters.left") },
  ];
  const chip = ({ value, label }: { value: Filter; label: string }) => (
    <button
      key={String(value)}
      type="button"
      role="radio"
      aria-checked={filter === value}
      onClick={() => setFilter(value)}
      className={`min-h-11 whitespace-nowrap rounded-full border-2 px-3 text-sm font-bold ${
        filter === value ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-4 pb-20 sm:pb-0">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display text-3xl font-extrabold tracking-tight">
          {t("pages.students")}
          {state.status === "success" && (
            <span className="ml-2 text-lg font-bold text-muted">{shown(state.data, filter).length}</span>
          )}
        </h1>
        {/* On a phone this is the floating button below. Neither shows offline (read only). */}
        {!readOnly && (
          <Link
            to="/students/new"
            className="hidden min-h-11 items-center gap-2 rounded-xl bg-brand px-4 font-bold text-brand-ink hover:opacity-90 sm:flex"
          >
            <PlusIcon className="h-5 w-5" />
            {t("students.add")}
          </Link>
        )}
      </div>

      <label className="flex min-h-12 items-center gap-2 rounded-xl border-2 border-line bg-surface px-3 focus-within:border-brand">
        <SearchIcon className="h-5 w-5 shrink-0 text-muted" />
        <span className="sr-only">{t("students.search")}</span>
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("pay.searchStudent")}
          className="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-placeholder"
        />
      </label>

      {/* Two rows that wrap rather than one that scrolls sideways, which hid the classes and
          "Anciens" off the edge of a phone. Smaller type is meant to keep the first row on one
          line at 375px with two-digit counts (by estimate); a longer one wraps, never hides. */}
      <div role="radiogroup" aria-label={t("students.filters.label")} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">{firstRow.map(chip)}</div>
        <div className="flex flex-wrap gap-2">{secondRow.map(chip)}</div>
      </div>

      <AsyncView
        state={state}
        onRetry={state.reload}
        isEmpty={(rows) => shown(rows, filter).length === 0}
        emptyMessage={t(filter === "owing" ? "home.allPaid" : "students.empty")}
      >
        {(rows) => (
          <StudentRows label={t("pages.students")}>
            {shown(rows, filter).map((s) => (
              <StudentRow
                key={s.id}
                to={`/students/${s.id}`}
                name={s.full_name}
                facts={[
                  ...(filter === "punctuality" && s.average_days_late !== null
                    ? [punctualityText(s.average_days_late)]
                    : moneyFacts({ monthsOverdue: s.months_overdue, drift: s.cumulative_drift })),
                  typeof filter !== "number" &&
                    (s.school_class ? `${s.school_class.level} ${s.school_class.name}` : t("classes.unassigned")),
                  s.is_repeating && t("student.repeatingShort"),
                ]}
                right={
                  filter === "punctuality" ? (
                    <PunctualityPill averageDaysLate={s.average_days_late} />
                  ) : (
                    <OwedPill
                      monthsOverdue={s.months_overdue}
                      amountOwed={s.amount_owed}
                      priceStatus={s.price_status}
                    />
                  )
                }
              />
            ))}
          </StudentRows>
        )}
      </AsyncView>

      {!readOnly && (
        <Link
          to="/students/new"
          className="fixed bottom-[calc(5.5rem+env(safe-area-inset-bottom))] right-4 z-30 flex h-14 items-center gap-2 rounded-2xl bg-brand px-5 font-bold text-brand-ink shadow-lg sm:hidden"
        >
          <PlusIcon className="h-5 w-5" />
          {t("students.addShort")}
        </Link>
      )}
    </div>
  );
}

/**
 * The rows a filter shows, in the order it shows them: who owes most first for "owing", the
 * latest payers first for "punctuality" (students with nothing due yet left out), the class's
 * students for a class, alphabetical otherwise. `Number` only compares amounts; nothing is
 * computed from them.
 */
function shown(rows: StudentListItem[], filter: Filter): StudentListItem[] {
  if (typeof filter === "number") {
    return rows
      .filter((s) => s.school_class?.id === filter)
      .sort((a, b) => a.full_name.localeCompare(b.full_name));
  }
  if (filter === "punctuality") {
    return rows
      .filter((s) => s.average_days_late !== null)
      .sort(
        (a, b) => (b.average_days_late ?? 0) - (a.average_days_late ?? 0) || a.full_name.localeCompare(b.full_name),
      );
  }
  if (filter === "owing") {
    return rows
      .filter((s) => s.months_overdue > 0)
      .sort((a, b) => Number(b.amount_owed) - Number(a.amount_owed) || a.full_name.localeCompare(b.full_name));
  }
  return [...rows].sort((a, b) => a.full_name.localeCompare(b.full_name));
}

/** A fetch that answered "nothing asked yet" (null) reads as still loading. */
function asLoaded<T>(state: AsyncState<T | null> & { reload: () => void }): AsyncState<T> & { reload: () => void } {
  if (state.status === "success" && state.data === null) return { status: "loading", reload: state.reload };
  return state as AsyncState<T> & { reload: () => void };
}
