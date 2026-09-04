import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { deleteClass, downloadClassRoster, getClass, listStudents } from "../api/endpoints";
import type { ClassDetailOut, StudentListItem } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { resolveErrorMessage } from "../lib/errors";
import { classLabel } from "../lib/classes";
import { formatMoney } from "../lib/money";
import { slugify } from "../lib/slug";
import { DriftBadge } from "../components/DriftBadge";
import { OverdueBadge } from "../components/OverdueBadge";
import {
  AsyncView,
  Button,
  Card,
  DataTable,
  Modal,
  PageHeader,
  TextField,
} from "../components/ui";
import { updateClass } from "../api/endpoints";

export function ClassDetail() {
  const { id } = useParams();
  const classId = Number(id);
  const navigate = useNavigate();

  // Two reads rather than one: the roster is the existing students endpoint filtered by class,
  // so there is a single representation of "a list of students" across the app.
  const state = useApi(
    () => Promise.all([getClass(classId), listStudents({ class_id: classId })]),
    [classId],
  );

  return (
    <div>
      <AsyncView state={state} onRetry={state.reload}>
        {([schoolClass, roster]) => (
          <ClassView
            schoolClass={schoolClass}
            roster={roster}
            onChanged={state.reload}
            onDeleted={() => navigate("/classes")}
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

  const actions = (
    <>
      <Button variant="secondary" onClick={() => setRenaming(true)}>
        {t("classes.rename")}
      </Button>
      <Button
        variant="secondary"
        onClick={() =>
          downloadClassRoster(schoolClass.id, `${slugify(label)}-roster.pdf`, schoolClass.as_of)
        }
      >
        {t("classes.downloadRoster")}
      </Button>
      <Button variant="danger" onClick={handleDelete} pending={remove.status === "pending"}>
        {t("classes.delete")}
      </Button>
    </>
  );

  return (
    <>
      <Link
        to="/classes"
        className="mb-2 inline-block text-sm text-slate-500 hover:underline dark:text-slate-400"
      >
        ← {t("classes.backToClasses")}
      </Link>
      <PageHeader title={label} actions={actions} />

      {actionError && (
        <p className="mb-4 text-sm text-rose-600 dark:text-rose-400">{actionError}</p>
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

      <Card className="mb-6">
        <div className="flex items-center gap-8">
          <Stat label={t("classes.students")} value={String(schoolClass.student_count)} />
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {t("classes.drift")}
            </p>
            <div className="mt-1">
              <DriftBadge drift={schoolClass.cumulative_drift} />
            </div>
          </div>
          <div className="ml-auto">
            {/* Pre-fills (and shows) the class on the enrolment form — never silently. */}
            <Link to={`/students/new?class_id=${schoolClass.id}`}>
              <Button>{t("classes.addStudent")}</Button>
            </Link>
          </div>
        </div>
      </Card>

      <DataTable
        rows={roster}
        keyOf={(s) => s.id}
        empty={
          <Card>
            <p className="text-sm text-slate-500 dark:text-slate-400">{t("classes.rosterEmpty")}</p>
          </Card>
        }
        rowClassName={() => "hover:bg-slate-50 dark:hover:bg-slate-800/50"}
        columns={[
          {
            key: "name",
            header: t("students.columns.name"),
            primary: true,
            cell: (s) => (
              <Link
                to={`/students/${s.id}`}
                className="font-medium text-slate-900 hover:underline dark:text-slate-100"
              >
                {s.full_name}
              </Link>
            ),
          },
          {
            key: "status",
            header: t("students.columns.status"),
            cell: (s) => (
              <span className="capitalize text-slate-600 dark:text-slate-300">
                {t(`status.${s.status}`)}
              </span>
            ),
          },
          {
            key: "price",
            header: t("students.columns.price"),
            align: "right",
            cell: (s) => formatMoney(s.monthly_price),
          },
          {
            key: "overdue",
            header: t("students.columns.overdue"),
            cell: (s) => <OverdueBadge monthsOverdue={s.months_overdue} />,
          },
          {
            key: "owed",
            header: t("students.columns.owed"),
            align: "right",
            cell: (s) => formatMoney(s.amount_owed),
          },
          {
            key: "drift",
            header: t("students.columns.drift"),
            cell: (s) => <DriftBadge drift={s.cumulative_drift} />,
          },
        ]}
      />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">{value}</p>
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
