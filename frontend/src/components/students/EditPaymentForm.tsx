import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { updatePayment } from "../../api/endpoints";
import type { LedgerEntry, PaymentUpdate } from "../../api/types";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { formatMoney } from "../../lib/money";
import { todayIso } from "../../lib/dates";
import { Button, DateField, MoneyField } from "../ui";

type Props = {
  studentId: number;
  /** The paid month being corrected: its amount and date start the form. */
  entry: LedgerEntry & { paid_date: string; amount: string };
  /** The student's current price; a corrected amount can't go above it (the server agrees). */
  monthlyPrice: string;
  onSuccess: () => void;
  onCancel: () => void;
};

/**
 * Fix a typo in a recorded payment: its amount or the day it was paid. The month it settles is
 * not here: moving a payment to another month is delete, then record the right month.
 *
 * Only what changed is sent, so fixing a date never re-checks an amount nobody touched (a payment
 * made before a price cut can be above today's price, and that is not an error).
 */
export function EditPaymentForm({ studentId, entry, monthlyPrice, onSuccess, onCancel }: Props) {
  const { t } = useTranslation();
  const update = useMutation(updatePayment);
  const originalAmount = entry.amount.replace(/\.0+$/, "");
  const [amount, setAmount] = useState(originalAmount);
  const [paidDate, setPaidDate] = useState(entry.paid_date);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  // A French keyboard types "199,5"; the API reads decimal points. A string edit, not a parse.
  const normalized = amount.trim().replace(",", ".");
  // Number() only compares here: "200" and "200.00" are the same amount.
  const amountChanged = Number(normalized) !== Number(entry.amount) || normalized === "";
  const dateChanged = paidDate !== entry.paid_date;
  const cap = Number(monthlyPrice) > 0 ? Number(monthlyPrice) : null;

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (amountChanged) {
      if (normalized === "" || Number.isNaN(Number(normalized)) || Number(normalized) <= 0) {
        next.amount = t("payment.validation.amountInvalid");
      } else if (cap !== null && Number(normalized) > cap) {
        next.amount = t("payment.validation.amountAbovePrice", { price: formatMoney(monthlyPrice) });
      }
    }
    if (!paidDate) next.paid_date = t("payment.validation.paidDateRequired");
    else if (paidDate > todayIso()) next.paid_date = t("payment.validation.paidDateFuture");
    return next;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const clientErrors = validate();
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) return;
    const body: PaymentUpdate = {};
    if (amountChanged) body.amount = normalized;
    if (dateChanged) body.paid_date = paidDate;
    try {
      await update.mutate(studentId, entry.cycle_number, body);
      onSuccess();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <MoneyField
        id="edit-payment-amount"
        label={t("payment.fields.amount")}
        value={amount}
        onChange={setAmount}
        hint={cap === null ? undefined : t("payment.hints.amountUpTo", { price: formatMoney(monthlyPrice) })}
        error={errors.amount}
        placeholder="200"
      />
      <DateField
        id="edit-payment-date"
        label={t("payment.fields.paidDate")}
        value={paidDate}
        onChange={setPaidDate}
        error={errors.paid_date}
      />
      {formError && <p className="text-sm font-bold text-bad">{formError}</p>}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          type="submit"
          pending={update.status === "pending"}
          disabled={!amountChanged && !dateChanged}
          className="min-h-12 text-lg sm:min-w-40"
        >
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}
