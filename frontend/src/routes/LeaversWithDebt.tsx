import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listLeaversWithDebt, writeOffDebt } from "../api/endpoints";
import type { DebtStatus } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { resolveErrorMessage } from "../lib/errors";
import { formatMoney } from "../lib/money";
import { ReportTabs } from "../components/ReportTabs";
import { formatDate } from "../lib/dates";
import { AsyncView, Button, Modal, TextField } from "../components/ui";
import { Figure } from "../components/report";
import { Avatar } from "../components/people";

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
    <div className="flex flex-col gap-5">
      <ReportTabs />

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
            <Figure label={t("debts.totalOwed")} value={formatMoney(data.total_owed)} alarming />
            <ul
              aria-label={t("pages.debts")}
              className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface"
            >
              {data.leavers.map((s) => (
                <li key={s.student.id}>
                  <Link
                    to={`/students/${s.student.id}`}
                    className="flex min-h-16 items-center gap-3 px-4 pb-2 pt-3 hover:bg-ground"
                  >
                    <Avatar name={s.student.full_name} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-bold">{s.student.full_name}</span>
                      <span className="block truncate text-sm text-muted">
                        {[
                          s.left_on && t("debts.leftOnDate", { date: formatDate(s.left_on) }),
                          t("owed.monthsUnpaid", { count: s.months_owed }),
                          s.student.phone,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="shrink-0 whitespace-nowrap rounded-full bg-bad-soft px-3 py-1 text-sm font-bold text-bad">
                      {formatMoney(s.amount_owed)}
                    </span>
                  </Link>
                  {/* Kept below the row and quiet: forgiving a debt is rare and permanent. */}
                  <div className="flex justify-end px-2 pb-2">
                    <Button variant="ghost" onClick={() => setWritingOff(s)} className="text-sm">
                      {t("debts.writeOff")}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
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
        <p className="text-muted">{t("debts.writeOffHint")}</p>
        <TextField
          id="writeoff-reason"
          label={t("debts.writeOffReason")}
          value={reason}
          onChange={setReason}
          error={error ?? undefined}
          required
        />
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>
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
