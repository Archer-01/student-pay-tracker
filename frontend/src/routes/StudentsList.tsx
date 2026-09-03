import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listClasses, listStudents } from "../api/endpoints";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { classLabel } from "../lib/classes";
import { DriftBadge } from "../components/DriftBadge";
import { OverdueBadge } from "../components/OverdueBadge";
import {
  AsyncView,
  PageHeader,
  Select,
  Table,
  TBody,
  Td,
  TextField,
  Th,
  THead,
  Tr,
} from "../components/ui";

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
    <>
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
    </>
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
          <Table>
            <THead>
              <Tr>
                <Th>{t("students.columns.name")}</Th>
                <Th>{t("students.columns.status")}</Th>
                <Th>{t("students.columns.class")}</Th>
                <Th>{t("students.columns.price")}</Th>
                <Th>{t("students.columns.overdue")}</Th>
                <Th>{t("students.columns.owed")}</Th>
                <Th>{t("students.columns.drift")}</Th>
              </Tr>
            </THead>
            <TBody>
              {rows.map((s) => (
                <Tr key={s.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <Td>
                    <Link
                      to={`/students/${s.id}`}
                      className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                    >
                      {s.full_name}
                    </Link>
                    {s.is_repeating && (
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        {t("student.repeatingShort")}
                      </span>
                    )}
                  </Td>
                  <Td className="capitalize text-slate-600 dark:text-slate-300">{t(`status.${s.status}`)}</Td>
                  <Td className="text-slate-600 dark:text-slate-300">
                    {s.school_class ? (
                      <Link to={`/classes/${s.school_class.id}`} className="hover:underline">
                        {classLabel(s.school_class)}
                      </Link>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">
                        {t("classes.unassigned")}
                      </span>
                    )}
                  </Td>
                  <Td className="text-slate-600 dark:text-slate-300">
                    {formatMoney(s.monthly_price)}
                  </Td>
                  <Td>
                    <OverdueBadge monthsOverdue={s.months_overdue} />
                  </Td>
                  <Td className="text-slate-600 dark:text-slate-300">
                    {formatMoney(s.amount_owed)}
                  </Td>
                  <Td>
                    <DriftBadge drift={s.cumulative_drift} />
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        )}
      </AsyncView>
    </div>
  );
}
