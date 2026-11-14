import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listClasses, listStudents } from "../api/endpoints";
import type { StudentListItem } from "../api/types";
import { useApi } from "../lib/useApi";
import { useDebounced } from "../lib/useDebounced";
import { usePaymentsVersion } from "../lib/paymentSheetContext";
import { useReadOnly } from "../lib/connectivity";
import { AsyncView } from "../components/ui";
import { OwedPill } from "../components/people";
import { StudentRow, StudentRows } from "../components/StudentRow";
import { useMoneyFacts } from "../lib/useMoneyFacts";
import { PlusIcon, SearchIcon } from "../components/icons";

/** "all" and "owing" are current students; "left" is everyone who has left; a number is a class. */
type Filter = "all" | "owing" | "left" | number;

/**
 * Everyone, one line each, alphabetical so a name is where you expect it. A large search box and
 * a row of chips replace the four crammed filters: "Doivent de l'argent" is one tap, each class
 * is one tap, and former students sit behind "Anciens" so the default list is the current year.
 */
export function StudentsList() {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 250);
  const moneyFacts = useMoneyFacts();
  const readOnly = useReadOnly();

  // Refreshes after a payment taken from the shared sheet, wherever it was opened.
  const paymentsVersion = usePaymentsVersion();
  const state = useApi(
    () =>
      listStudents({
        status: filter === "left" ? "inactive" : "active",
        class_id: typeof filter === "number" ? filter : undefined,
        q: q || undefined,
      }),
    [filter, q, paymentsVersion],
  );
  // Class chips. A failure here must not blank the page; the chips simply don't appear.
  const classes = useApi(() => listClasses(), []);

  const chips: { value: Filter; label: string }[] = [
    { value: "all", label: t("students.filters.all") },
    { value: "owing", label: t("students.filters.owing") },
    ...(classes.data ?? []).map((c) => ({ value: c.id as Filter, label: `${c.level} ${c.name}` })),
    { value: "left", label: t("students.filters.left") },
  ];

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

      <div
        role="radiogroup"
        aria-label={t("students.filters.label")}
        className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0"
      >
        {chips.map((chip) => (
          <button
            key={String(chip.value)}
            type="button"
            role="radio"
            aria-checked={filter === chip.value}
            onClick={() => setFilter(chip.value)}
            className={`min-h-11 shrink-0 whitespace-nowrap rounded-full border-2 px-4 font-bold ${
              filter === chip.value ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink"
            }`}
          >
            {chip.label}
          </button>
        ))}
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
                  ...moneyFacts({ monthsOverdue: s.months_overdue, drift: s.cumulative_drift }),
                  typeof filter !== "number" &&
                    (s.school_class ? `${s.school_class.level} ${s.school_class.name}` : t("classes.unassigned")),
                  s.is_repeating && t("student.repeatingShort"),
                ]}
                right={
                  <OwedPill
                    monthsOverdue={s.months_overdue}
                    amountOwed={s.amount_owed}
                    monthlyPrice={s.monthly_price}
                  />
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
 * The rows a filter shows, in the order it shows them: who owes most first for "owing",
 * alphabetical otherwise. `Number` only compares amounts; nothing is computed from them.
 */
function shown(rows: StudentListItem[], filter: Filter): StudentListItem[] {
  if (filter === "owing") {
    return rows
      .filter((s) => s.months_overdue > 0)
      .sort((a, b) => Number(b.amount_owed) - Number(a.amount_owed) || a.full_name.localeCompare(b.full_name));
  }
  return [...rows].sort((a, b) => a.full_name.localeCompare(b.full_name));
}
