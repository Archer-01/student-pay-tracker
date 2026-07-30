import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { updateStudent } from "../../api/endpoints";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { Button, MoneyField, Select, TextField } from "../ui";

type Props = {
  studentId: number;
  initial: { phone: string | null; fee: string; status: "active" | "inactive" };
  onSuccess: () => void;
  onCancel: () => void;
};

export function EditStudentForm({ studentId, initial, onSuccess, onCancel }: Props) {
  const { t } = useTranslation();
  const update = useMutation(updateStudent);

  const [phone, setPhone] = useState(initial.phone ?? "");
  const [fee, setFee] = useState(initial.fee);
  const [status, setStatus] = useState<"active" | "inactive">(initial.status);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (fee.trim() === "" || Number.isNaN(Number(fee)) || Number(fee) < 0) {
      next.fee = t("edit.validation.feeInvalid");
    }
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
      await update.mutate(studentId, { phone: phone.trim() || null, fee, status });
      onSuccess();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <TextField
        id="edit-phone"
        label={t("edit.fields.phone")}
        value={phone}
        onChange={setPhone}
        error={errors.phone}
      />
      <MoneyField id="edit-fee" label={t("edit.fields.fee")} value={fee} onChange={setFee} error={errors.fee} required />
      <Select
        id="edit-status"
        label={t("edit.fields.status")}
        value={status}
        onChange={(value) => setStatus(value as "active" | "inactive")}
        options={[
          { value: "active", label: t("status.active") },
          { value: "inactive", label: t("status.inactive") },
        ]}
        error={errors.status}
      />
      {formError && <p className="text-sm text-rose-600">{formError}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" pending={update.status === "pending"}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}
