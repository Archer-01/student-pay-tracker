import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createClass, listClasses } from "../api/endpoints";
import type { ClassLevel } from "../api/types";
import { useApi } from "../lib/useApi";
import { useReadOnly } from "../lib/connectivity";
import { useMutation } from "../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../lib/errors";
import { CLASS_LEVELS } from "../lib/classes";
import { AsyncView, Button, Modal, Select, TextField } from "../components/ui";
import { ChevronLeftIcon, ChevronRightIcon, PlusIcon } from "../components/icons";

/**
 * Réglages › Classes: one line per class with its size and lateness. Set up at the start of the
 * year and rarely touched after, which is why it lives under Réglages rather than in the bar.
 */
export function ClassesList() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const readOnly = useReadOnly();
  const state = useApi(() => listClasses(), []);

  return (
    <div className="flex flex-col gap-4">
      <Link to="/settings" className="-ml-1 flex min-h-11 items-center gap-1 self-start font-bold text-brand">
        <ChevronLeftIcon className="h-5 w-5" />
        {t("nav.settings")}
      </Link>
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display text-3xl font-extrabold tracking-tight">{t("pages.classes")}</h1>
        <Button onClick={() => setCreating(true)} disabled={readOnly}>
          <PlusIcon className="h-5 w-5" />
          {t("classes.create")}
        </Button>
      </div>

      {creating && (
        <CreateClassModal
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            state.reload();
          }}
        />
      )}

      <AsyncView
        state={state}
        onRetry={state.reload}
        isEmpty={(rows) => rows.length === 0}
        emptyMessage={t("classes.empty")}
      >
        {(rows) => (
          <ul
            aria-label={t("pages.classes")}
            className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface"
          >
            {rows.map((c) => (
              <li key={c.id}>
                <Link to={`/settings/classes/${c.id}`} className="flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-ground">
                  <span className="flex h-10 min-w-12 shrink-0 items-center justify-center rounded-xl bg-brand-soft px-2 text-sm font-bold text-brand">
                    {c.level}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-bold">{c.name}</span>
                    <span className="block truncate text-sm text-muted">
                      {[
                        t("dashboard.activeStudents", { count: c.student_count }),
                        c.cumulative_drift > 0 && t("home.lateTotal", { count: c.cumulative_drift }),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <ChevronRightIcon className="h-5 w-5 text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </div>
  );
}

function CreateClassModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const create = useMutation(createClass);
  const [level, setLevel] = useState<ClassLevel>(CLASS_LEVELS[0]);
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!name.trim()) {
      setErrors({ name: t("classes.validation.nameRequired") });
      return;
    }
    setErrors({});
    try {
      await create.mutate({ level, name: name.trim() });
      onCreated();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={t("classes.createTitle")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Select
          id="class-level"
          label={t("classes.level")}
          value={level}
          onChange={(value) => setLevel(value as ClassLevel)}
          options={CLASS_LEVELS.map((l) => ({ value: l, label: l }))}
        />
        <TextField
          id="class-name"
          label={t("classes.name")}
          value={name}
          onChange={setName}
          hint={t("classes.namePlaceholder")}
          error={errors.name}
          required
        />
        {formError && <p className="text-sm text-rose-600 dark:text-rose-400">{formError}</p>}
        <Button type="submit" pending={create.status === "pending"} className="w-full">
          {t("classes.create")}
        </Button>
      </form>
    </Modal>
  );
}
