import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { updateStudent } from "../../api/endpoints";
import { useMutation } from "../../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../../lib/errors";
import { Button, Modal, TextAreaField } from "../ui";

/** The server's limit on a note (backend `NOTE_MAX_LENGTH`), as in `EditStudentForm`. */
const NOTE_MAX_LENGTH = 500;

type Props = {
  studentId: number;
  /** Who the note is about, for the title: the field below is already called "Note". */
  name: string;
  note: string | null;
  onSaved: () => void;
  onClose: () => void;
};

/**
 * The student's private note on its own, opened straight from the page: jotting "pays on
 * Saturdays" shouldn't mean scrolling past the name, class and price. Only the note is sent, so
 * nothing else about the student can change by accident.
 */
export function NoteSheet({ studentId, name, note, onSaved, onClose }: Props) {
  const { t } = useTranslation();
  const update = useMutation(updateStudent);
  const [value, setValue] = useState(note ?? "");
  const [error, setError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const trimmed = value.trim();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    setFormError(null);
    try {
      // An emptied field sends an explicit null: that is how a note is removed.
      await update.mutate(studentId, { note: trimmed || null });
      onSaved();
    } catch (err) {
      const fields = fieldErrors(err);
      if (fields.note) setError(fields.note);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={t("student.noteTitle", { name })} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <TextAreaField
          id="note-sheet"
          label={t("edit.fields.note")}
          value={value}
          onChange={setValue}
          hint={t("edit.noteHint")}
          error={error}
          placeholder={t("edit.notePlaceholder")}
          maxLength={NOTE_MAX_LENGTH}
          rows={4}
        />
        {formError && <p className="text-sm font-bold text-bad">{formError}</p>}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={update.status === "pending"} disabled={trimmed === (note ?? "").trim()}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
