import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getLedger, getStudent } from "../api/endpoints";
import { downloadFile } from "../api/client";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate } from "../lib/dates";
import { slugify } from "../lib/slug";
import { resolveErrorMessage } from "../lib/errors";
import { DriftBadge } from "../components/DriftBadge";
import { OverdueBadge } from "../components/OverdueBadge";
import { RecordPaymentForm } from "../components/students/RecordPaymentForm";
import { CreateOverrideForm } from "../components/students/CreateOverrideForm";
import { EditStudentForm } from "../components/students/EditStudentForm";
import type { LedgerEntry } from "../api/types";
import { AsyncView, Button, Card, Modal, PageHeader, Table, TBody, THead, Th, Td, Tr } from "../components/ui";

type OpenModal = null | "payment" | "override" | "edit";

export function StudentDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const studentId = Number(id);

  const state = useApi(
    () => Promise.all([getStudent(studentId), getLedger(studentId)]),
    [studentId],
  );

  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [openModal, setOpenModal] = useState<OpenModal>(null);

  const close = () => setOpenModal(null);
  const handleSaved = () => {
    close();
    state.reload();
  };

  async function handleDownload(name: string) {
    setDownloadError(null);
    try {
      const slug = slugify(name);
      const stem = t("detail.pdfFilename", { id: studentId, name: slug ? `-${slug}` : "" });
      await downloadFile(`/students/${studentId}/ledger.pdf`, `${stem}.pdf`);
    } catch (err) {
      setDownloadError(resolveErrorMessage(err, t));
    }
  }

  return (
    <div>
      <Link
        to="/students"
        className="mb-4 inline-block text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      >
        ← {t("detail.back")}
      </Link>

      <AsyncView state={state} onRetry={state.reload}>
        {([detail, ledger]) => (
          <>
            <PageHeader
              title={detail.name}
              actions={
                <div className="flex flex-col items-end gap-1">
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button onClick={() => setOpenModal("payment")}>{t("detail.actions.recordPayment")}</Button>
                    <Button variant="secondary" onClick={() => setOpenModal("override")}>
                      {t("detail.actions.addOverride")}
                    </Button>
                    <Button variant="secondary" onClick={() => setOpenModal("edit")}>
                      {t("detail.actions.edit")}
                    </Button>
                    <Button variant="ghost" onClick={() => handleDownload(detail.name)}>
                      {t("detail.downloadPdf")}
                    </Button>
                  </div>
                  {downloadError && (
                    <span className="text-xs text-rose-600 dark:text-rose-400">{downloadError}</span>
                  )}
                </div>
              }
            />

            {openModal === "payment" && (
              <Modal title={t("payment.title")} onClose={close}>
                <RecordPaymentForm studentId={studentId} onSuccess={handleSaved} onCancel={close} />
              </Modal>
            )}
            {openModal === "override" && (
              <Modal title={t("override.title")} onClose={close}>
                <CreateOverrideForm studentId={studentId} onSuccess={handleSaved} onCancel={close} />
              </Modal>
            )}
            {openModal === "edit" && (
              <Modal title={t("edit.title")} onClose={close}>
                <EditStudentForm
                  studentId={studentId}
                  initial={{ phone: detail.phone, fee: detail.fee, status: detail.status }}
                  onSuccess={handleSaved}
                  onCancel={close}
                />
              </Modal>
            )}

            <Card className="mb-6">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
                <Stat label={t("detail.fields.status")}>{t(`status.${detail.status}`)}</Stat>
                <Stat label={t("detail.fields.fee")}>{formatMoney(detail.fee)}</Stat>
                <Stat label={t("detail.fields.joinDate")}>{formatDate(detail.join_date)}</Stat>
                <Stat label={t("detail.fields.drift")}>
                  <DriftBadge drift={detail.cumulative_drift} />
                </Stat>
                <Stat label={t("detail.fields.overdue")}>
                  <OverdueBadge monthsOverdue={detail.months_overdue} />
                </Stat>
                <Stat label={t("detail.fields.nextExpected")}>{formatDate(detail.next_expected_date)}</Stat>
                <Stat label={t("detail.fields.paymentsCount")}>{detail.payments_count}</Stat>
                <Stat label={t("detail.fields.totalPaid")}>{formatMoney(detail.total_paid)}</Stat>
                {detail.phone && <Stat label={t("detail.fields.phone")}>{detail.phone}</Stat>}
              </dl>
            </Card>

            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {t("ledger.title")}
            </h2>
            <Table>
              <THead>
                <Tr>
                  <Th>{t("ledger.columns.cycle")}</Th>
                  <Th>{t("ledger.columns.due")}</Th>
                  <Th>{t("ledger.columns.paid")}</Th>
                  <Th>{t("ledger.columns.status")}</Th>
                  <Th>{t("ledger.columns.amount")}</Th>
                  <Th>{t("ledger.columns.drift")}</Th>
                </Tr>
              </THead>
              <TBody>
                {ledger.entries.map((entry) => {
                  const unpaid = entry.paid_date === null;
                  return (
                    <Tr key={entry.cycle_number} className={unpaid ? "text-slate-400 dark:text-slate-500" : ""}>
                      <Td>{entry.cycle_number}</Td>
                      <Td>{formatDate(entry.expected_due_date)}</Td>
                      <Td>{entry.paid_date ? formatDate(entry.paid_date) : "—"}</Td>
                      <Td>{ledgerStatus(entry, t)}</Td>
                      <Td>{entry.amount !== null ? formatMoney(entry.amount) : "—"}</Td>
                      <Td>{entry.cumulative_drift}</Td>
                    </Tr>
                  );
                })}
              </TBody>
            </Table>
          </>
        )}
      </AsyncView>
    </div>
  );
}

function ledgerStatus(entry: LedgerEntry, t: ReturnType<typeof useTranslation>["t"]): string {
  if (entry.paid_date === null) return t("ledger.status.unpaid");
  if (entry.days_late !== null && entry.days_late > 0) return t("drift.late", { count: entry.days_late });
  return t("ledger.status.onTime");
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">{children}</dd>
    </div>
  );
}
