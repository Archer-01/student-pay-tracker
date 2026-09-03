import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listLeaversWithDebt, writeOffDebt } from "../api/endpoints";
import type { DebtStatus } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { resolveErrorMessage } from "../lib/errors";
import { formatMoney } from "../lib/money";
import { formatDate } from "../lib/dates";
import {
  AsyncView,
  Button,
  Card,
  Modal,
  PageHeader,
  Table,
  TBody,
  Td,
  TextField,
  Th,
  THead,
  Tr,
} from "../components/ui";

/**
 * Students who left owing money.
 *
 * Deliberately a list, not a gate: nothing in the app refuses to re-admit someone who owes. Its
 * whole job is to make sure the teacher knows before they decide.
 */
export function LeaversWithDebt() {
  const { t } = useTranslation();
  const [writingOff, setWritingOff] = useState<DebtStatus | null>(null);
  const state = useApi(() => listLeaversWithDebt(), []);

  return (
    <div>
      <PageHeader title={t("pages.debts")} />

      {writingOff && (
        <WriteOffModal
          status={writingOff}
          onClose={() => setWritingOff(null)}
          onDone={() => {
            setWritingOff(null);
            state.reload();
          }}
        />
      )}

      <AsyncView
        state={state}
        onRetry={state.reload}
        isEmpty={(data) => data.leavers.length === 0}
        emptyMessage={t("debts.empty")}
      >
        {(data) => (
          <>
            <Card className="mb-6">
              <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {t("debts.totalOwed")}
              </p>
              <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
                {formatMoney(data.total_owed)}
              </p>
            </Card>

            <Table>
              <THead>
                <Tr>
                  <Th>{t("students.columns.name")}</Th>
                  <Th>{t("detail.fields.phone")}</Th>
                  <Th>{t("debts.leftOn")}</Th>
                  <Th>{t("debts.months")}</Th>
                  <Th>{t("debts.owed")}</Th>
                  <Th> </Th>
                </Tr>
              </THead>
              <TBody>
                {data.leavers.map((status) => (
                  <Tr key={status.student.id}>
                    <Td>
                      <Link
                        to={`/students/${status.student.id}`}
                        className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                      >
                        {status.student.full_name}
                      </Link>
                    </Td>
                    <Td className="text-slate-600 dark:text-slate-300">
                      {status.student.phone ?? "—"}
                    </Td>
                    <Td className="text-slate-600 dark:text-slate-300">
                      {status.left_on ? formatDate(status.left_on) : "—"}
                    </Td>
                    <Td className="text-slate-600 dark:text-slate-300">{status.months_owed}</Td>
                    <Td className="font-medium text-rose-700 dark:text-rose-400">
                      {formatMoney(status.amount_owed)}
                    </Td>
                    <Td>
                      <Button variant="ghost" onClick={() => setWritingOff(status)}>
                        {t("debts.writeOff")}
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          </>
        )}
      </AsyncView>
    </div>
  );
}

function WriteOffModal({
  status,
  onClose,
  onDone,
}: {
  status: DebtStatus;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const writeOff = useMutation(writeOffDebt);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!reason.trim()) {
      setError(t("debts.writeOffReason"));
      return;
    }
    try {
      await writeOff.mutate(status.student.id, { reason: reason.trim() });
      onDone();
    } catch (err) {
      setError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal
      title={t("debts.writeOffTitle", { name: status.student.full_name })}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Said plainly: writing off is bookkeeping, not income. The alternative — recording a
            payment that never happened — would quietly inflate the revenue reports. */}
        <p className="text-xs text-slate-500 dark:text-slate-400">{t("debts.writeOffHint")}</p>
        <TextField
          id="writeoff-reason"
          label={t("debts.writeOffReason")}
          value={reason}
          onChange={setReason}
          error={error ?? undefined}
          required
        />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" variant="danger" pending={writeOff.status === "pending"}>
            {t("debts.writeOffConfirm", { amount: formatMoney(status.amount_owed) })}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
