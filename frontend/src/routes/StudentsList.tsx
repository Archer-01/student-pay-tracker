import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listClasses, listStudents } from "../api/endpoints";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { classLabel } from "../lib/classes";
import { DriftBadge } from "../components/DriftBadge";
import { OverdueBadge } from "../components/OverdueBadge";
import { AsyncView, Button, DataTable, PageHeader, Select, TextField } from "../components/ui";

type StatusFilter = "" | "active" | "inactive";

export function StudentsList() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<StatusFilter>("active");
  const [classId, setClassId] = useState("");
  const [search, setSearch] = useState("");

  const state = useApi(
    () =>
      listStudents({
        status: status || undefined,
        class_id: classId ? Number(classId) : undefined,
        q: search.trim() || undefined,
        sort: "drift_desc",
      }),
    [status, classId, search],
  );
  // Populates the class filter. A failure here must not blank the page, so the options simply
  // fall back to "all classes" rather than being surfaced as a page-level error.
  const classes = useApi(() => listClasses(), []);

  const filter = (
    <div className="flex items-end gap-2">
      <TextField
        id="students-search"
        label={t("students.search")}
        value={search}
        onChange={setSearch}
        placeholder={t("students.searchPlaceholder")}
      />
      <Select
        id="students-class-filter"
        label={t("classes.filterLevel")}
        value={classId}
        onChange={setClassId}
        options={[
          { value: "", label: t("students.filterClassAll") },
          ...(classes.data ?? []).map((c) => ({ value: String(c.id), label: classLabel(c) })),
        ]}
      />
      <Select
        id="students-status-filter"
        label={t("students.filterLabel")}
        value={status}
        onChange={(value) => setStatus(value as StatusFilter)}
        options={[
          { value: "", label: t("students.filterAll") },
          { value: "active", label: t("status.active") },
          { value: "inactive", label: t("status.inactive") },
        ]}
      />
      {/* Enrolling is an action, so it lives on the page you're already on rather than in the
          nav bar next to the destinations. */}
      <Link to="/students/new">
        <Button className="mb-[1px] whitespace-nowrap">{t("students.add")}</Button>
      </Link>
    </div>
  );

  return (
    <div>
      <PageHeader title={t("pages.students")} actions={filter} />

      <AsyncView
        state={state}
        onRetry={state.reload}
        isEmpty={(rows) => rows.length === 0}
        emptyMessage={t("students.empty")}
      >
        {(rows) => (
          <DataTable
            rows={rows}
            keyOf={(s) => s.id}
            rowClassName={() => "hover:bg-slate-50 dark:hover:bg-slate-800/50"}
            columns={[
              {
                key: "name",
                header: t("students.columns.name"),
                primary: true,
                cell: (s) => (
                  <>
                    <Link
                      to={`/students/${s.id}`}
                      className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                    >
                      {s.full_name}
                    </Link>
                    {s.is_repeating && (
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-normal text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        {t("student.repeatingShort")}
                      </span>
                    )}
                  </>
                ),
              },
              {
                key: "status",
                header: t("students.columns.status"),
                cell: (s) => (
                  <span className="capitalize text-slate-600 dark:text-slate-300">
                    {t(`status.${s.status}`)}
                  </span>
                ),
              },
              {
                key: "class",
                header: t("students.columns.class"),
                cell: (s) =>
                  s.school_class ? (
                    <Link to={`/classes/${s.school_class.id}`} className="hover:underline">
                      {classLabel(s.school_class)}
                    </Link>
                  ) : (
                    <span className="text-slate-400 dark:text-slate-500">
                      {t("classes.unassigned")}
                    </span>
                  ),
              },
              {
                key: "price",
                header: t("students.columns.price"),
                align: "right",
                cell: (s) => formatMoney(s.monthly_price),
              },
              {
                key: "overdue",
                header: t("students.columns.overdue"),
                cell: (s) => <OverdueBadge monthsOverdue={s.months_overdue} />,
              },
              {
                key: "owed",
                header: t("students.columns.owed"),
                align: "right",
                cell: (s) => formatMoney(s.amount_owed),
              },
              {
                key: "drift",
                header: t("students.columns.drift"),
                cell: (s) => <DriftBadge drift={s.cumulative_drift} />,
              },
            ]}
          />
        )}
      </AsyncView>
    </div>
  );
}
