import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listStudents } from "../api/endpoints";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { DriftBadge } from "../components/DriftBadge";
import { OverdueBadge } from "../components/OverdueBadge";
import { AsyncView, PageHeader, Select, Table, TBody, THead, Th, Td, Tr } from "../components/ui";

type StatusFilter = "" | "active" | "inactive";

export function StudentsList() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<StatusFilter>("active");

  const state = useApi(
    () => listStudents({ status: status || undefined, sort: "drift_desc" }),
    [status],
  );

  const filter = (
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
                <Th>{t("students.columns.fee")}</Th>
                <Th>{t("students.columns.overdue")}</Th>
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
                      {s.name}
                    </Link>
                  </Td>
                  <Td className="capitalize text-slate-600 dark:text-slate-300">{t(`status.${s.status}`)}</Td>
                  <Td className="text-slate-600 dark:text-slate-300">{formatMoney(s.fee)}</Td>
                  <Td>
                    <OverdueBadge monthsOverdue={s.months_overdue} />
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
