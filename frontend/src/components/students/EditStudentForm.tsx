import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { listClasses, updateStudent } from "../../api/endpoints";
import { useApi } from "../../lib/useApi";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { classLabel } from "../../lib/classes";
import { NameFields } from "./NameFields";
import { PricingFields } from "./PricingFields";
import { Button, Select, TextAreaField, TextField } from "../ui";

/** The server's limit on a note (backend `NOTE_MAX_LENGTH`). */
const NOTE_MAX_LENGTH = 500;

type Props = {
  studentId: number;
  initial: {
    firstName: string;
    lastName: string | null;
    isRepeating: boolean;
    phone: string | null;
    classId: number | null;
    packId: number | null;
    customPrice: string | null;
    priceNote: string | null;
    note: string | null;
  };
  onSuccess: () => void;
  onCancel: () => void;
};

/**
 * Who the student is and what they pay. Deliberately no "Statut" field: setting a student
 * inactive here recorded no departure date, so billing carried on for someone marked as gone.
 * Departures and returns go through "Marquer comme parti" / "Réinscrire", which record the date.
 */
export function EditStudentForm({ studentId, initial, onSuccess, onCancel }: Props) {
  const { t } = useTranslation();
  const update = useMutation(updateStudent);

  const [firstName, setFirstName] = useState(initial.firstName);
  const [lastName, setLastName] = useState(initial.lastName ?? "");
  const [isRepeating, setIsRepeating] = useState(initial.isRepeating);
  const [phone, setPhone] = useState(initial.phone ?? "");

  const [classId, setClassId] = useState(initial.classId === null ? "" : String(initial.classId));
  const [packId, setPackId] = useState(initial.packId === null ? "" : String(initial.packId));
  const [customPrice, setCustomPrice] = useState(initial.customPrice ?? "");
  const [priceNote, setPriceNote] = useState(initial.priceNote ?? "");
  const [note, setNote] = useState(initial.note ?? "");
  // A failure here must not block editing phone/fee/status, so the options degrade to just
  // "no class" rather than surfacing as a form error.
  const classes = useApi(() => listClasses(), []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!firstName.trim()) next.first_name = t("edit.validation.firstNameRequired");
    if (customPrice.trim() !== "" && (Number.isNaN(Number(customPrice)) || Number(customPrice) < 0)) {
      next.custom_price = t("edit.validation.priceInvalid");
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
      // class_id is always sent: an explicit null is what unassigns a student, so omitting the
      // key (which the backend reads as "leave unchanged") would make clearing it impossible.
      await update.mutate(studentId, {
        first_name: firstName.trim(),
        // Explicit null means "no surname on record", not "unchanged".
        last_name: lastName.trim() || null,
        is_repeating: isRepeating,
        phone: phone.trim() || null,
        class_id: classId ? Number(classId) : null,
        pack_id: packId ? Number(packId) : null,
        // An explicit null clears the arrangement and returns them to the pack price.
        custom_price: customPrice.trim() === "" ? null : customPrice,
        price_note: priceNote.trim() || null,
        // Always sent, like the class: an explicit null is how a note is removed.
        note: note.trim() || null,
      });
      onSuccess();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <NameFields
        firstName={firstName}
        onFirstName={setFirstName}
        lastName={lastName}
        onLastName={setLastName}
        errors={errors}
      />
      <TextField
        id="edit-phone"
        label={t("edit.fields.phone")}
        value={phone}
        onChange={setPhone}
        error={errors.phone}
      />
      <Select
        id="edit-class"
        label={t("edit.fields.class")}
        value={classId}
        onChange={setClassId}
        options={[
          { value: "", label: t("classes.none") },
          ...(classes.data ?? []).map((c) => ({ value: String(c.id), label: classLabel(c) })),
        ]}
        error={errors.class_id}
      />
      <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
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
        errors={errors}
      />
      <TextAreaField
        id="edit-note"
        label={t("edit.fields.note")}
        value={note}
        onChange={setNote}
        hint={t("edit.noteHint")}
        error={errors.note}
        placeholder={t("edit.notePlaceholder")}
        maxLength={NOTE_MAX_LENGTH}
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
