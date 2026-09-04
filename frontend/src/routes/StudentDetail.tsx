import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getLedger, getStudent, listPeriods } from "../api/endpoints";
import { downloadFile } from "../api/client";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate } from "../lib/dates";
import { classLabel } from "../lib/classes";
import { slugify } from "../lib/slug";
import { resolveErrorMessage } from "../lib/errors";
import { DriftBadge } from "../components/DriftBadge";
import { OverdueBadge } from "../components/OverdueBadge";
import { RecordPaymentForm } from "../components/students/RecordPaymentForm";
import { CreateOverrideForm } from "../components/students/CreateOverrideForm";
import { EditStudentForm } from "../components/students/EditStudentForm";
import { AttendanceForm } from "../components/students/AttendanceForm";
import type { LedgerEntry } from "../api/types";
import {
  AsyncView,
  Button,
  Card,
  DataTable,
  Modal,
  PageHeader,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
} from "../components/ui";

type OpenModal = null | "payment" | "override" | "edit" | "leave" | "return";

export function StudentDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const studentId = Number(id);

  const state = useApi(
    () => Promise.all([getStudent(studentId), getLedger(studentId), listPeriods(studentId)]),
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
        {([detail, ledger, periods]) => (
          <>
            <PageHeader
              title={detail.full_name}
              actions={
                <div className="flex flex-col items-end gap-1">
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button onClick={() => setOpenModal("payment")}>{t("detail.actions.recordPayment")}</Button>
                    <Button variant="secondary" onClick={() => setOpenModal("override")}>
                      {t("detail.actions.addOverride")}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => setOpenModal(detail.status === "active" ? "leave" : "return")}
                    >
                      {t(detail.status === "active" ? "student.markLeft" : "student.markReturned")}
                    </Button>
                    <Button variant="secondary" onClick={() => setOpenModal("edit")}>
                      {t("detail.actions.edit")}
                    </Button>
                    <Button variant="ghost" onClick={() => handleDownload(detail.full_name)}>
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
            {(openModal === "leave" || openModal === "return") && (
              <Modal
                title={t(openModal === "leave" ? "student.leaveTitle" : "student.returnTitle")}
                onClose={close}
              >
                <AttendanceForm
                  studentId={studentId}
                  mode={openModal}
                  onSuccess={handleSaved}
                  onCancel={close}
                />
              </Modal>
            )}
            {openModal === "edit" && (
              <Modal title={t("edit.title")} onClose={close}>
                <EditStudentForm
                  studentId={studentId}
                  initial={{
                    firstName: detail.first_name,
                    lastName: detail.last_name,
                    isRepeating: detail.is_repeating,
                    phone: detail.phone,
                    status: detail.status,
                    classId: detail.class_id,
                    packId: detail.pack_id,
                    customPrice: detail.custom_price,
                    priceNote: detail.price_note,
                  }}
                  onSuccess={handleSaved}
                  onCancel={close}
                />
              </Modal>
            )}

            {/* Two groups rather than fourteen tiles in a row: who they are and what they're
                signed up for, then the money. The split is how the teacher actually reads the
                page — the second block is the one they open it for. */}
            <Card className="mb-4">
              <SectionLabel>{t("detail.sections.enrolment")}</SectionLabel>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
                <Stat label={t("detail.fields.status")}>{t(`status.${detail.status}`)}</Stat>
                <Stat label={t("detail.fields.class")}>
                  {detail.school_class ? (
                    <Link to={`/classes/${detail.school_class.id}`} className="hover:underline">
                      {classLabel(detail.school_class)}
                    </Link>
                  ) : (
                    <span className="font-normal text-slate-400 dark:text-slate-500">
                      {t("classes.unassigned")}
                    </span>
                  )}
                </Stat>
                <Stat label={t("student.pack")}>
                  {detail.pack ? (
                    <>
                      {detail.pack.name} · {detail.pack.level}
                      {/* The pack's level disagreeing with the class is allowed but worth
                          seeing — usually a mis-click, occasionally deliberate. */}
                      {detail.school_class &&
                        detail.school_class.level !== detail.pack.level && (
                          <span
                            className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs font-normal text-amber-700 dark:bg-amber-950 dark:text-amber-400"
                            title={t("student.levelMismatch", {
                              packLevel: detail.pack.level,
                              classLevel: detail.school_class.level,
                            })}
                          >
                            {detail.school_class.level} ≠ {detail.pack.level}
                          </span>
                        )}
                    </>
                  ) : (
                    /* No pack means no price, so they are billed nothing — the dashboard flags
                       this too, but it should be obvious on the student's own page. */
                    <span className="font-normal text-amber-700 dark:text-amber-400">
                      {t("student.noPack")}
                    </span>
                  )}
                </Stat>
                <Stat label={t("detail.fields.monthlyPrice")}>
                  {formatMoney(detail.monthly_price)}
                  {/* An agreed price is shown against the pack's, so the exception is visible. */}
                  {detail.custom_price !== null && detail.pack && (
                    <span className="ml-1 text-xs font-normal text-amber-700 dark:text-amber-400">
                      {t("student.insteadOf", { price: formatMoney(detail.pack.price) })}
                      {detail.price_note ? ` · ${detail.price_note}` : ""}
                    </span>
                  )}
                </Stat>
                <Stat label={t("detail.fields.joinDate")}>{formatDate(detail.join_date)}</Stat>
                {/* Shown unconditionally: an empty phone is information too, and a grid that
                    changes shape per student is harder to scan. */}
                <Stat label={t("detail.fields.phone")}>
                  {detail.phone ?? <span className="font-normal text-slate-400">—</span>}
                </Stat>
                <Stat label={t("detail.fields.repeating")}>
                  {detail.is_repeating ? t("common.yes") : t("common.no")}
                </Stat>
              </dl>
            </Card>

            <Card className="mb-6">
              <SectionLabel>{t("detail.sections.money")}</SectionLabel>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
                <Stat label={t("detail.fields.amountOwed")}>
                  {formatMoney(detail.amount_owed)}
                </Stat>
                <Stat label={t("detail.fields.overdue")}>
                  <OverdueBadge monthsOverdue={detail.months_overdue} />
                </Stat>
                <Stat label={t("detail.fields.drift")}>
                  <DriftBadge drift={detail.cumulative_drift} />
                </Stat>
                <Stat label={t("detail.fields.nextExpected")}>
                  {formatDate(detail.next_expected_date)}
                </Stat>
                <Stat label={t("detail.fields.totalPaid")}>{formatMoney(detail.total_paid)}</Stat>
                <Stat label={t("detail.fields.paymentsCount")}>{detail.payments_count}</Stat>
                <Stat label={t("detail.fields.firstPayment")}>
                  {detail.first_payment_date ? formatDate(detail.first_payment_date) : "—"}
                </Stat>
              </dl>
            </Card>

            {/* Only worth a section once there's an actual absence — a single open period
                since the join date is already shown as "Student since". */}
            {periods.length > 1 && (
              <>
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  {t("student.attendance")}
                </h2>
                <div className="mb-6">
                  <Table>
                    <THead>
                      <Tr>
                        <Th>{t("student.from")}</Th>
                        <Th>{t("student.until")}</Th>
                        <Th>{t("student.reason")}</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {periods.map((p) => (
                        <Tr key={p.id}>
                          <Td>{formatDate(p.entry_date)}</Td>
                          <Td>
                            {p.leave_date ? (
                              formatDate(p.leave_date)
                            ) : (
                              <span className="text-emerald-700 dark:text-emerald-400">
                                {t("student.stillHere")}
                              </span>
                            )}
                          </Td>
                          <Td className="text-slate-400 dark:text-slate-500">
                            {p.leave_reason ?? "—"}
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </div>
              </>
            )}

            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {t("ledger.title")}
            </h2>
            <DataTable
              rows={ledger.entries}
              keyOf={(entry) => entry.cycle_number}
              rowClassName={(entry) =>
                // An away month is styled distinctly from an unpaid one: it is not a debt, and
                // colouring them alike is the mistake worth avoiding here.
                entry.suspended
                  ? "bg-slate-50 italic text-slate-400 dark:bg-slate-800/40 dark:text-slate-500"
                  : entry.paid_date === null
                    ? "text-slate-400 dark:text-slate-500"
                    : ""
              }
              columns={[
                {
                  key: "due",
                  header: t("ledger.columns.due"),
                  primary: true,
                  cell: (entry) => (
                    <>
                      {formatDate(entry.expected_due_date)}
                      <span className="ml-2 text-xs font-normal text-slate-400">
                        #{entry.cycle_number}
                      </span>
                    </>
                  ),
                },
                {
                  key: "cycle",
                  header: t("ledger.columns.cycle"),
                  // Folded into the due-date heading on a phone, where a bare index earns nothing.
                  wideOnly: true,
                  cell: (entry) => entry.cycle_number,
                },
                {
                  key: "paid",
                  header: t("ledger.columns.paid"),
                  cell: (entry) => (entry.paid_date ? formatDate(entry.paid_date) : "—"),
                },
                {
                  key: "status",
                  header: t("ledger.columns.status"),
                  cell: (entry) => ledgerStatus(entry, t),
                },
                {
                  key: "amount",
                  header: t("ledger.columns.amount"),
                  align: "right",
                  cell: (entry) => (entry.amount !== null ? formatMoney(entry.amount) : "—"),
                },
                {
                  key: "drift",
                  header: t("ledger.columns.drift"),
                  align: "right",
                  wideOnly: true,
                  cell: (entry) => entry.cumulative_drift,
                },
              ]}
            />
          </>
        )}
      </AsyncView>
    </div>
  );
}

function ledgerStatus(entry: LedgerEntry, t: ReturnType<typeof useTranslation>["t"]): string {
  // "Away" takes precedence over "Unpaid": a month the student wasn't enrolled for is not a debt.
  if (entry.suspended) return t("ledger.status.away");
  if (entry.paid_date === null) return t("ledger.status.unpaid");
  if (entry.days_late !== null && entry.days_late > 0) return t("drift.late", { count: entry.days_late });
  return t("ledger.status.onTime");
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
      {children}
    </h2>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">{children}</dd>
    </div>
  );
}
