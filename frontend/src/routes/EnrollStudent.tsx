import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createStudent } from "../api/endpoints";
import { useMutation } from "../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../lib/errors";
import { Button, Card, DateField, MoneyField, PageHeader, TextField } from "../components/ui";

export function EnrollStudent() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useMutation(createStudent);

  const [name, setName] = useState("");
  const [joinDate, setJoinDate] = useState("");
  const [fee, setFee] = useState("");
  const [phone, setPhone] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = t("enroll.validation.nameRequired");
    if (fee.trim() === "" || Number.isNaN(Number(fee)) || Number(fee) < 0) {
      next.fee = t("enroll.validation.feeInvalid");
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
      const student = await create.mutate({
        name: name.trim(),
        join_date: joinDate,
        fee, // stays a string — never coerce money to a number
        phone: phone.trim() || undefined,
        status: "active",
      });
      navigate(`/students/${student.id}`);
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <div>
      <PageHeader title={t("pages.enroll")} />
      <Card className="max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <TextField
            id="enroll-name"
            label={t("enroll.fields.name")}
            value={name}
            onChange={setName}
            error={errors.name}
            required
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
          <MoneyField
            id="enroll-fee"
            label={t("enroll.fields.fee")}
            value={fee}
            onChange={setFee}
            error={errors.fee}
            required
          />
          <TextField
            id="enroll-phone"
            label={t("enroll.fields.phone")}
            value={phone}
            onChange={setPhone}
            error={errors.phone}
          />

          {formError && <p className="text-sm text-rose-600 dark:text-rose-400">{formError}</p>}

          <Button type="submit" pending={create.status === "pending"} className="w-full">
            {t("enroll.submit")}
          </Button>
        </form>
      </Card>
    </div>
  );
}
