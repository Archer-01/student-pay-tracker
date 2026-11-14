import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { deleteClass, downloadClassRoster, getClass, listStudents } from "../api/endpoints";
import type { ClassDetailOut, StudentListItem } from "../api/types";
import { useApi } from "../lib/useApi";
import { useReadOnly } from "../lib/connectivity";
import { useMutation } from "../lib/useMutation";
import { resolveErrorMessage } from "../lib/errors";
import { classLabel } from "../lib/classes";
import { slugify } from "../lib/slug";
import { AsyncView, Button, Modal, TextField } from "../components/ui";
import { OwedPill } from "../components/people";
import { StudentRow, StudentRows } from "../components/StudentRow";
import { ChevronLeftIcon, PlusIcon } from "../components/icons";
import { useMoneyFacts } from "../lib/useMoneyFacts";
import { updateClass } from "../api/endpoints";
import { usePaymentsVersion } from "../lib/paymentSheetContext";

export function ClassDetail() {
  const { id } = useParams();
  const classId = Number(id);
  const navigate = useNavigate();

  // Two reads rather than one: the roster is the existing students endpoint filtered by class,
  // so there is a single representation of "a list of students" across the app.
  // Refreshes after a payment taken from the shared sheet, wherever it was opened.
  const paymentsVersion = usePaymentsVersion();
  const state = useApi(
    () => Promise.all([getClass(classId), listStudents({ class_id: classId })]),
    [classId, paymentsVersion],
  );

  return (
    <div>
      <AsyncView state={state} onRetry={state.reload}>
        {([schoolClass, roster]) => (
          <ClassView
            schoolClass={schoolClass}
            roster={roster}
            onChanged={state.reload}
            onDeleted={() => navigate("/settings/classes")}
          />
        )}
      </AsyncView>
    </div>
  );
}

function ClassView({
  schoolClass,
  roster,
  onChanged,
  onDeleted,
}: {
  schoolClass: ClassDetailOut;
  roster: StudentListItem[];
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation();
  const [renaming, setRenaming] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const remove = useMutation(deleteClass);
  const moneyFacts = useMoneyFacts();
  const readOnly = useReadOnly();
  const label = classLabel(schoolClass);

  async function handleDelete() {
    if (!window.confirm(t("classes.deleteConfirm"))) return;
    setActionError(null);
    try {
      await remove.mutate(schoolClass.id);
      onDeleted();
    } catch (err) {
      // The common failure is a 409: the class still has students. Show the backend's
      // already-localized detail rather than guessing at the reason.
      setActionError(resolveErrorMessage(err, t));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Link to="/settings/classes" className="-ml-1 flex min-h-11 items-center gap-1 self-start font-bold text-brand">
        <ChevronLeftIcon className="h-5 w-5" />
        {t("classes.backToClasses")}
      </Link>
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-3xl font-extrabold tracking-tight">{label}</h1>
        <p className="text-muted">
          {[
            t("dashboard.activeStudents", { count: schoolClass.student_count }),
            schoolClass.cumulative_drift > 0 && t("home.lateTotal", { count: schoolClass.cumulative_drift }),
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </header>

      {/* Pre-fills (and shows) the class on the enrolment form, never silently. */}
      {!readOnly && (
        <Link
          to={`/students/new?class_id=${schoolClass.id}`}
          className="flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand px-5 font-bold text-brand-ink hover:opacity-90 sm:self-start"
        >
          <PlusIcon className="h-5 w-5" />
          {t("classes.addStudent")}
        </Link>
      )}

      {renaming && (
        <RenameClassModal
          schoolClass={schoolClass}
          onClose={() => setRenaming(false)}
          onRenamed={() => {
            setRenaming(false);
            onChanged();
          }}
        />
      )}

      {roster.length === 0 ? (
        <p className="rounded-2xl border border-line bg-surface p-4 text-muted">{t("classes.rosterEmpty")}</p>
      ) : (
        <StudentRows label={label}>
          {[...roster]
            .sort((a, b) => a.full_name.localeCompare(b.full_name))
            .map((s) => (
              <StudentRow
                key={s.id}
                to={`/students/${s.id}`}
                name={s.full_name}
                facts={[
                  ...moneyFacts({ monthsOverdue: s.months_overdue, drift: s.cumulative_drift }),
                  s.status === "inactive" && t("student.leftTitle"),
                ]}
                right={
                  <OwedPill monthsOverdue={s.months_overdue} amountOwed={s.amount_owed} monthlyPrice={s.monthly_price} />
                }
              />
            ))}
        </StudentRows>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button variant="secondary" onClick={() => setRenaming(true)} disabled={readOnly}>
          {t("classes.rename")}
        </Button>
        <Button
          variant="secondary"
          onClick={() => downloadClassRoster(schoolClass.id, `${slugify(label)}-roster.pdf`, schoolClass.as_of)}
        >
          {t("classes.downloadRoster")}
        </Button>
      </div>

      {/* Alone at the bottom, away from the everyday buttons: deleting is rare and needs the
          class to be empty first. */}
      <div className="flex flex-col gap-2 border-t border-line pt-5">
        <Button
          variant="ghost"
          onClick={handleDelete}
          pending={remove.status === "pending"}
          disabled={readOnly}
          className="text-bad sm:self-start"
        >
          {t("classes.delete")}
        </Button>
        {actionError && <p className="text-sm font-bold text-bad">{actionError}</p>}
      </div>
    </div>
  );
}

function RenameClassModal({
  schoolClass,
  onClose,
  onRenamed,
}: {
  schoolClass: ClassDetailOut;
  onClose: () => void;
  onRenamed: () => void;
}) {
  const { t } = useTranslation();
  const rename = useMutation(updateClass);
  const [name, setName] = useState(schoolClass.name);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError(t("classes.validation.nameRequired"));
      return;
    }
    try {
      await rename.mutate(schoolClass.id, { name: name.trim() });
      onRenamed();
    } catch (err) {
      setError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={t("classes.renameTitle")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <TextField
          id="class-rename"
          label={t("classes.name")}
          value={name}
          onChange={setName}
          error={error ?? undefined}
          required
        />
        <Button type="submit" pending={rename.status === "pending"} className="w-full">
          {t("classes.rename")}
        </Button>
      </form>
    </Modal>
  );
}
