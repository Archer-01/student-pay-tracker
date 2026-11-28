import { isZeroAmount } from "../../lib/money";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { listClasses, updateStudent } from "../../api/endpoints";
import { useApi } from "../../lib/useApi";
import { useMutation } from "../../lib/useMutation";
import { ApiError } from "../../api/client";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { formatDate } from "../../lib/dates";
import { classLabel } from "../../lib/classes";
import { NameFields } from "./NameFields";
import { PricingFields } from "./PricingFields";
import { Button, ConfirmBox, DateField, Select, TextAreaField, TextField } from "../ui";

/** The server's refusals of a join date correction (decision 0015). Some lock the date for good;
 *  the others only rule out the date chosen, so another can still be tried. */
const JOIN_DATE_LOCKED = ["join_date_has_payments", "join_date_has_writeoffs"];
const JOIN_DATE_REFUSED = ["join_date_after_payment_day", "join_date_after_leave"];

/** Brings a field with an error into view: the sheet scrolls, and the field can be far above. */
function reveal(id: string) {
  document.getElementById(id)?.scrollIntoView?.({ block: "center", behavior: "smooth" });
}

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
    joinDate: string;
    /** Payments recorded: while there are any, the join date is locked (decision 0015). */
    paymentsCount: number;
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
  const [joinDate, setJoinDate] = useState(initial.joinDate);
  // Locked up front while payments are recorded; locked after the server refuses for another
  // reason (a changed payment day, a debt no longer claimed), so the next save goes through.
  // The server's reason, kept as the field's hint once it has locked the date.
  const [lockedBecause, setLockedBecause] = useState<string | null>(null);
  const joinDateLocked = initial.paymentsCount > 0 || lockedBecause !== null;
  // A failure here must not block editing phone/fee/status, so the options degrade to just
  // "no class" rather than surfacing as a form error.
  const classes = useApi(() => listClasses(), []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  // The questions asked before saving (a price of 0, a corrected join date), or null.
  const [asking, setAsking] = useState<string[] | null>(null);

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!firstName.trim()) next.first_name = t("edit.validation.firstNameRequired");
    if (!joinDate) next.join_date = t("edit.validation.joinDateRequired");
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
      if (clientErrors.join_date) reveal("edit-join-date");
      return;
    }
    setErrors({});
    const questions = [
      // Asked only when the price becomes 0 here, not on every save of a student already free.
      ...(isZeroAmount(customPrice) && !isZeroAmount(initial.customPrice ?? "")
        ? [t("student.freeConfirm")]
        : []),
      // A slip in the date picker would recompute every month.
      ...(joinDate !== initial.joinDate
        ? [t("edit.joinDateConfirm", { date: formatDate(joinDate) })]
        : []),
    ];
    if (questions.length > 0) setAsking(questions);
    else await save();
  }

  async function save() {
    const joinDateChanged = joinDate !== initial.joinDate;
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
        // Sent only when corrected: the server refuses any change once payments depend on it,
        // so a plain save of a student with payments must not carry it.
        ...(joinDateChanged ? { join_date: joinDate } : {}),
      });
      onSuccess();
    } catch (err) {
      setAsking(null);
      if (err instanceof ApiError && err.code && JOIN_DATE_LOCKED.includes(err.code)) {
        // Said under the field it is about, with the date put back and locked.
        const reason = resolveErrorMessage(err, t);
        setErrors({ join_date: reason });
        setJoinDate(initial.joinDate);
        setLockedBecause(reason);
        reveal("edit-join-date");
        return;
      }
      if (err instanceof ApiError && err.code && JOIN_DATE_REFUSED.includes(err.code)) {
        // This date only: said under the field, which stays open for another.
        setErrors({ join_date: resolveErrorMessage(err, t) });
        reveal("edit-join-date");
        return;
      }
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
      <DateField
        id="edit-join-date"
        label={t("edit.fields.joinDate")}
        value={joinDate}
        onChange={setJoinDate}
        disabled={joinDateLocked}
        hint={
          lockedBecause ??
          (initial.paymentsCount > 0
            ? t("edit.joinDateLocked", { count: initial.paymentsCount })
            : t("edit.joinDateHint"))
        }
        error={errors.join_date}
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
      {formError && <p className="text-sm font-bold text-bad">{formError}</p>}
      {asking ? (
        <ConfirmBox
          messages={asking}
          pending={update.status === "pending"}
          onConfirm={() => void save()}
          onCancel={() => setAsking(null)}
        />
      ) : (
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={update.status === "pending"}>
            {t("common.save")}
          </Button>
        </div>
      )}
    </form>
  );
}
