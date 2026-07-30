import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createOverride } from "../../api/endpoints";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { Button, DateField, TextField } from "../ui";

type Props = { studentId: number; onSuccess: () => void; onCancel: () => void };

export function CreateOverrideForm({ studentId, onSuccess, onCancel }: Props) {
  const { t } = useTranslation();
  const create = useMutation(createOverride);

  const [newDueDate, setNewDueDate] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!newDueDate) next.new_due_date = t("override.validation.newDueDateRequired");
    if (!reason.trim()) next.reason = t("override.validation.reasonRequired");
    return next;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const clientErrors = validate();
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      return;
    }
    setErrors({});
    try {
      await create.mutate(studentId, { new_due_date: newDueDate, reason: reason.trim() });
      onSuccess();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <DateField
        id="override-new-due-date"
        label={t("override.fields.newDueDate")}
        value={newDueDate}
        onChange={setNewDueDate}
        error={errors.new_due_date}
        required
      />
      <TextField
        id="override-reason"
        label={t("override.fields.reason")}
        value={reason}
        onChange={setReason}
        error={errors.reason}
        required
      />
      {formError && <p className="text-sm text-rose-600">{formError}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" pending={create.status === "pending"}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}
