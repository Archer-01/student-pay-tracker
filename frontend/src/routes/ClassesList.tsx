import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createClass, listClasses } from "../api/endpoints";
import type { ClassLevel } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../lib/errors";
import { CLASS_LEVELS } from "../lib/classes";
import { DriftBadge } from "../components/DriftBadge";
import {
  AsyncView,
  Button,
  Modal,
  PageHeader,
  Select,
  Table,
  TBody,
  Td,
  Th,
  TextField,
  THead,
  Tr,
} from "../components/ui";

type LevelFilter = "" | ClassLevel;

export function ClassesList() {
  const { t } = useTranslation();
  const [level, setLevel] = useState<LevelFilter>("");
  const [creating, setCreating] = useState(false);

  const state = useApi(() => listClasses({ level: level || undefined }), [level]);

  // items-end + mb-[1px]: the Select renders a label above its input, so a bare Button would
  // centre against the whole stack and float above the input. Same pattern as MonthlyReport.
  const actions = (
    <div className="flex items-end gap-2">
      <Select
        id="classes-level-filter"
        label={t("classes.filterLevel")}
        value={level}
        onChange={(value) => setLevel(value as LevelFilter)}
        options={[
          { value: "", label: t("classes.filterAll") },
          ...CLASS_LEVELS.map((l) => ({ value: l, label: l })),
        ]}
      />
      <Button onClick={() => setCreating(true)} className="mb-[1px] whitespace-nowrap">
        {t("classes.create")}
      </Button>
    </div>
  );

  return (
    <div>
      <PageHeader title={t("pages.classes")} actions={actions} />

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
          <Table>
            <THead>
              <Tr>
                <Th>{t("classes.level")}</Th>
                <Th>{t("classes.name")}</Th>
                <Th>{t("classes.students")}</Th>
                <Th>{t("classes.drift")}</Th>
              </Tr>
            </THead>
            <TBody>
              {rows.map((c) => (
                <Tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <Td className="text-slate-600 dark:text-slate-300">{c.level}</Td>
                  <Td>
                    <Link
                      to={`/classes/${c.id}`}
                      className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                    >
                      {c.name}
                    </Link>
                  </Td>
                  <Td className="text-slate-600 dark:text-slate-300">{c.student_count}</Td>
                  <Td>
                    <DriftBadge drift={c.cumulative_drift} />
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
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
