import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { recordLeave, recordReturn } from "../../api/endpoints";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { Button, DateField, TextField } from "../ui";

type Props = {
  studentId: number;
  mode: "leave" | "return";
  onSuccess: () => void;
  onCancel: () => void;
};

/**
 * Record a departure or a return.
 *
 * Neither moves the student's join date: the billing schedule still runs from the anchor, so a
 * returning student keeps the drift and the debt they left with. A return is deliberately not
 * blocked by an outstanding balance — whether to re-admit someone who owes is the teacher's call.
 */
export function AttendanceForm({ studentId, mode, onSuccess, onCancel }: Props) {
  const { t } = useTranslation();
  const leaving = mode === "leave";
  // Two mutations rather than one picked at runtime: the request bodies differ, and a union of
  // the two functions isn't callable with either body.
  const leave = useMutation(recordLeave);
  const back = useMutation(recordReturn);
  const pending = (leaving ? leave : back).status === "pending";

  const [when, setWhen] = useState(new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  // A return is never refused, so the debt comes back in the response rather than as an error.
  // Show it and make the teacher acknowledge it instead of closing silently.
  const [debtWarning, setDebtWarning] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setErrors({});
    try {
      if (leaving) {
        await leave.mutate(studentId, { leave_date: when, reason: reason.trim() || undefined });
      } else {
        const result = await back.mutate(studentId, { entry_date: when });
        if (result.debt_warning) {
          setDebtWarning(result.debt_warning);
          return; // the return already happened; this is an acknowledgement, not a gate
        }
      }
      onSuccess();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  if (debtWarning) {
    return (
      <div className="space-y-4">
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <strong className="block">{t("debts.returnedWithDebt")}</strong>
          {debtWarning}
        </p>
        <div className="flex justify-end">
          <Button onClick={onSuccess}>{t("common.close", { defaultValue: "Close" })}</Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <DateField
        id="attendance-date"
        label={t(leaving ? "student.leaveDate" : "student.returnDate")}
        value={when}
        onChange={setWhen}
        hint={t(leaving ? "student.leaveHint" : "student.returnHint")}
        error={errors.leave_date ?? errors.entry_date}
        required
      />
      {leaving && (
        <TextField
          id="attendance-reason"
          label={t("student.leaveReason")}
          value={reason}
          onChange={setReason}
          error={errors.reason}
        />
      )}
      {formError && <p className="text-sm text-rose-600 dark:text-rose-400">{formError}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" pending={pending}>
          {t(leaving ? "student.markLeft" : "student.markReturned")}
        </Button>
      </div>
    </form>
  );
}
