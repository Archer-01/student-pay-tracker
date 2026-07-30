import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { recordPayment } from "../../api/endpoints";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { Button, DateField, MoneyField, MonthField } from "../ui";

type Props = { studentId: number; onSuccess: () => void; onCancel: () => void };

export function RecordPaymentForm({ studentId, onSuccess, onCancel }: Props) {
  const { t } = useTranslation();
  const create = useMutation(recordPayment);

  const [forMonth, setForMonth] = useState("");
  const [paidDate, setPaidDate] = useState("");
  const [amount, setAmount] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!forMonth) next.for_month = t("payment.validation.monthRequired");
    if (!paidDate) next.paid_date = t("payment.validation.paidDateRequired");
    if (amount.trim() === "" || Number.isNaN(Number(amount)) || Number(amount) <= 0) {
      next.amount = t("payment.validation.amountInvalid");
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
      // Always send for_month (never cycle_number) — satisfies the backend's XOR by construction.
      await create.mutate(studentId, { paid_date: paidDate, amount, for_month: forMonth });
      onSuccess();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <MonthField
        id="payment-for-month"
        label={t("payment.fields.forMonth")}
        value={forMonth}
        onChange={setForMonth}
        error={errors.for_month}
        required
      />
      <DateField
        id="payment-paid-date"
        label={t("payment.fields.paidDate")}
        value={paidDate}
        onChange={setPaidDate}
        error={errors.paid_date}
        required
      />
      <MoneyField
        id="payment-amount"
        label={t("payment.fields.amount")}
        value={amount}
        onChange={setAmount}
        error={errors.amount}
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
