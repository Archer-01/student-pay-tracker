import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createStudent, findSimilarLeavers, listClasses } from "../api/endpoints";
import { useApi } from "../lib/useApi";
import { useDebounced } from "../lib/useDebounced";
import { useMutation } from "../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../lib/errors";
import { classLabel } from "../lib/classes";
import { formatMoney, isZeroAmount} from "../lib/money";
import { NameFields } from "../components/students/NameFields";
import { PricingFields } from "../components/students/PricingFields";
import { Button, Card, DateField, Select, TextField } from "../components/ui";
import { ChevronLeftIcon } from "../components/icons";

export function EnrollStudent() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useMutation(createStudent);

  // Arriving from a class page ("Add student") pre-selects that class. The field stays visible
  // and editable — pre-filling invisibly is how you end up with students in the wrong class.
  const [searchParams] = useSearchParams();
  const presetClassId = searchParams.get("class_id") ?? "";
  const classes = useApi(() => listClasses(), []);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [isRepeating, setIsRepeating] = useState(false);
  // Usually the day the student turns up; still editable for back-filling an earlier start.
  const [joinDate, setJoinDate] = useState(todayIso);

  const [phone, setPhone] = useState("");
  const [classId, setClassId] = useState(presetClassId);
  const [packId, setPackId] = useState("");
  const [customPrice, setCustomPrice] = useState("");
  const [priceNote, setPriceNote] = useState("");
  // The obvious loophole is re-enrolling a debtor under a fresh record. Checked as they type the
  // name or phone, and shown as a warning — real people share names, so it never blocks.
  //
  // Debounced: the lookup scans every student, and firing it per keystroke sent a dozen requests
  // to answer one question.
  const lookup = useDebounced({
    first: firstName.trim(),
    last: lastName.trim(),
    phone: phone.trim(),
  });
  const similar = useApi(
    () =>
      lookup.first || lookup.phone
        ? findSimilarLeavers({
            first_name: lookup.first || undefined,
            last_name: lookup.last || undefined,
            phone: lookup.phone || undefined,
          })
        : Promise.resolve([]),
    [lookup],
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!firstName.trim()) next.first_name = t("enroll.validation.firstNameRequired");
    if (customPrice.trim() !== "" && (Number.isNaN(Number(customPrice)) || Number(customPrice) < 0)) {
      next.custom_price = t("enroll.validation.priceInvalid");
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
    // A price of 0 means a student who is never chased (decision 0011): make sure it's meant.
    if (isZeroAmount(customPrice) && !window.confirm(t("student.freeConfirm"))) return;
    try {
      const student = await create.mutate({
        first_name: firstName.trim(),
        last_name: lastName.trim() || undefined,
        is_repeating: isRepeating,
        join_date: joinDate,
        phone: phone.trim() || undefined,
        status: "active",
        class_id: classId ? Number(classId) : undefined,
        pack_id: packId ? Number(packId) : undefined,
        // Money stays a string — never coerce it to a number.
        custom_price: customPrice.trim() === "" ? undefined : customPrice,
        price_note: priceNote.trim() || undefined,
      });
      navigate(`/students/${student.id}`);
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Link to="/students" className="-ml-1 flex min-h-11 items-center gap-1 self-start font-bold text-brand">
        <ChevronLeftIcon className="h-5 w-5" />
        {t("nav.students")}
      </Link>
      <h1 className="font-display text-3xl font-extrabold tracking-tight">{t("pages.enroll")}</h1>
      <Card className="max-w-lg">
        <form onSubmit={handleSubmit} className="space-y-4">
          <NameFields
            firstName={firstName}
            onFirstName={setFirstName}
            lastName={lastName}
            onLastName={setLastName}
            errors={errors}
          />
          <DateField
            id="enroll-join-date"
            label={t("enroll.fields.joinDate")}
            value={joinDate}
            onChange={setJoinDate}
            hint={t("enroll.joinDateHint")}
            error={errors.join_date}
            required
          />
          <TextField
            id="enroll-phone"
            label={t("enroll.fields.phone")}
            value={phone}
            onChange={setPhone}
            error={errors.phone}
          />
          <Select
            id="enroll-class"
            label={t("enroll.fields.class")}
            value={classId}
            onChange={setClassId}
            error={errors.class_id}
            options={[
              { value: "", label: t("classes.none") },
              ...(classes.data ?? []).map((c) => ({
                value: String(c.id),
                label: classLabel(c),
              })),
            ]}
          />
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={isRepeating}
              onChange={(e) => setIsRepeating(e.target.checked)}
            />
            {t("student.repeating")}
          </label>
          <PricingFields
            packId={packId}
            onPackId={setPackId}
            customPrice={customPrice}
            onCustomPrice={setCustomPrice}
            priceNote={priceNote}
            onPriceNote={setPriceNote}
            classLevel={(classes.data ?? []).find((c) => String(c.id) === classId)?.level}
            pickFromClass
            errors={errors}
          />

          {(similar.data ?? []).map((match) => (
            <p
              key={match.student.id}
              className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              {t("debts.duplicateWarning", { amount: formatMoney(match.amount_owed) })}{" "}
              <Link to={`/students/${match.student.id}`} className="underline">
                {match.student.full_name}
              </Link>
            </p>
          ))}

          {formError && <p className="text-sm text-rose-600 dark:text-rose-400">{formError}</p>}

          <Button type="submit" pending={create.status === "pending"} className="w-full">
            {t("enroll.submit")}
          </Button>
        </form>
      </Card>
    </div>
  );
}

/** Today as `YYYY-MM-DD` in the teacher's own timezone, the format a date input takes. */
function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
