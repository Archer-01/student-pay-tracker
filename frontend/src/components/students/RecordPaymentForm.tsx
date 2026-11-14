import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { getLedger, getStudent, recordPayment } from "../../api/endpoints";
import type { LedgerOut, StudentDetailOut } from "../../api/types";
import { useApi } from "../../lib/useApi";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { formatMoney } from "../../lib/money";
import { formatMonthTitle } from "../../lib/dates";
import { defaultAmount, payableMonths } from "../../lib/paymentDefaults";
import { AsyncView, Button, DateField, MoneyField } from "../ui";
import { Avatar } from "../people";

/** Today as `YYYY-MM-DD` in the teacher's own timezone, comparable with a date input's value. */
function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

type Props = {
  studentId: number;
  /** Called with the amount actually sent and the student's name, for the confirmation. */
  onSuccess: (amount: string, studentName: string) => void;
  onCancel: () => void;
  /** Offered when the sheet started from the student picker: go back and pick someone else. */
  onChangeStudent?: () => void;
};

export function RecordPaymentForm({ studentId, onSuccess, onCancel, onChangeStudent }: Props) {
  const state = useApi(() => Promise.all([getStudent(studentId), getLedger(studentId)]), [studentId]);
  return (
    <AsyncView state={state} onRetry={state.reload}>
      {([student, ledger]) => (
        <PaymentFields
          student={student}
          ledger={ledger}
          onSuccess={onSuccess}
          onCancel={onCancel}
          onChangeStudent={onChangeStudent}
        />
      )}
    </AsyncView>
  );
}

/**
 * Opens filled in: the oldest month still owed, the amount paid last time (never above the
 * price), and today. In the usual case the teacher checks it and presses one button.
 */
function PaymentFields({
  student,
  ledger,
  onSuccess,
  onCancel,
  onChangeStudent,
}: {
  student: StudentDetailOut;
  ledger: LedgerOut;
} & Omit<Props, "studentId">) {
  const { t } = useTranslation();
  const create = useMutation(recordPayment);
  const months = payableMonths(ledger.entries, student.next_expected_date);
  const hasPaidBefore = ledger.entries.some((e) => e.paid_date !== null);
  const price = student.monthly_price;
  const cap = Number(price) > 0 ? Number(price) : null;

  const [forMonth, setForMonth] = useState(months[0]!.month);
  const [amount, setAmount] = useState(() => defaultAmount(ledger.entries, price));
  const [paidToday, setPaidToday] = useState(true);
  const [otherDate, setOtherDate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  // A French keyboard types "200,50"; the API reads decimal points. A string edit, not a parse.
  const normalized = amount.trim().replace(",", ".");
  const paidDate = paidToday ? todayIso() : otherDate;

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!paidDate) next.paid_date = t("payment.validation.paidDateRequired");
    // The server refuses this too, but with an English validation message.
    else if (paidDate > todayIso()) next.paid_date = t("payment.validation.paidDateFuture");
    if (normalized === "" || Number.isNaN(Number(normalized)) || Number(normalized) <= 0) {
      next.amount = t("payment.validation.amountInvalid");
    } else if (cap !== null && Number(normalized) > cap) {
      next.amount = t("payment.validation.amountAbovePrice", { price: formatMoney(price) });
    }
    return next;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const clientErrors = validate();
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) return;
    try {
      await create.mutate(student.id, { paid_date: paidDate, amount: normalized, for_month: forMonth });
      onSuccess(normalized, student.full_name);
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  const amountHint =
    cap === null
      ? undefined
      : hasPaidBefore
        ? t("pay.amountHintRepeat", { price: formatMoney(price) })
        : t("pay.amountHintFirst", { price: formatMoney(price) });

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex items-center gap-3 rounded-2xl border border-line p-3">
        <Avatar name={student.full_name} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-bold">{student.full_name}</p>
          <p className="truncate text-sm text-muted">
            {student.months_overdue > 0
              ? t("pay.owes", { count: student.months_overdue, amount: formatMoney(student.amount_owed) })
              : t("pay.upToDate")}
          </p>
        </div>
        {onChangeStudent && (
          <button type="button" onClick={onChangeStudent} className="min-h-11 px-2 font-bold text-brand">
            {t("pay.change")}
          </button>
        )}
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-bold">{t("pay.month")}</legend>
        <div className="flex flex-wrap gap-2">
          {months.map((m) => (
            <Chip key={m.month} name="for_month" checked={forMonth === m.month} onChange={() => setForMonth(m.month)}>
              {formatMonthTitle(m.month)}
              {!m.overdue && <span className="ml-1.5 font-normal opacity-80">· {t("pay.inAdvance")}</span>}
            </Chip>
          ))}
        </div>
      </fieldset>

      <MoneyField
        id="payment-amount"
        label={t("payment.fields.amount")}
        value={amount}
        onChange={setAmount}
        hint={amountHint}
        error={errors.amount}
        placeholder="200"
      />

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-bold">{t("pay.paidOn")}</legend>
        <div className="flex flex-wrap gap-2">
          <Chip name="paid_on" checked={paidToday} onChange={() => setPaidToday(true)}>
            {t("pay.today")}
          </Chip>
          <Chip name="paid_on" checked={!paidToday} onChange={() => setPaidToday(false)}>
            {t("pay.otherDate")}
          </Chip>
        </div>
        {!paidToday && (
          <DateField
            id="payment-paid-date"
            label={t("payment.fields.paidDate")}
            value={otherDate}
            onChange={setOtherDate}
            error={errors.paid_date}
          />
        )}
        {paidToday && errors.paid_date && <p className="text-sm font-bold text-bad">{errors.paid_date}</p>}
      </fieldset>

      {formError && <p className="text-sm font-bold text-bad">{formError}</p>}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" pending={create.status === "pending"} className="min-h-12 text-lg sm:min-w-48">
          {normalized && !Number.isNaN(Number(normalized)) && Number(normalized) > 0
            ? t("pay.submit", { amount: formatMoney(normalized) })
            : t("pay.submitEmpty")}
        </Button>
      </div>
    </form>
  );
}

/** A radio button that looks like a pill: easier to hit, and all choices visible at once. */
function Chip({
  name,
  checked,
  onChange,
  children,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  children: React.ReactNode;
}) {
  return (
    <label
      className={`flex min-h-11 cursor-pointer items-center rounded-full border-2 px-4 font-bold has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand ${
        checked ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink"
      }`}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className="sr-only" />
      {children}
    </label>
  );
}
