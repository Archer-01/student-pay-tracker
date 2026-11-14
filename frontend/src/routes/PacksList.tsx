import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createPack, deletePack, listPacks, updatePack } from "../api/endpoints";
import type { ClassLevel, PackDetail, PackUpdate } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../lib/errors";
import { formatMoney } from "../lib/money";
import { CLASS_LEVELS } from "../lib/classes";
import { AsyncView, Button, Modal, MoneyField, Select, TextField } from "../components/ui";
import { ChevronLeftIcon, PlusIcon } from "../components/icons";

/**
 * Réglages › Packs: every pack on its own line. A pack is one name at one level with its own
 * subjects and price, created and edited on its own; nothing here groups packs across levels.
 */
export function PacksList() {
  const { t } = useTranslation();
  const state = useApi(() => listPacks(), []);
  const [editing, setEditing] = useState<PackDetail | "new" | null>(null);

  const done = () => {
    setEditing(null);
    state.reload();
  };

  return (
    <div className="flex flex-col gap-4">
      <Link to="/settings" className="-ml-1 flex min-h-11 items-center gap-1 self-start font-bold text-brand">
        <ChevronLeftIcon className="h-5 w-5" />
        {t("nav.settings")}
      </Link>
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display text-3xl font-extrabold tracking-tight">{t("packs.title")}</h1>
        <Button onClick={() => setEditing("new")}>
          <PlusIcon className="h-5 w-5" />
          {t("packs.new")}
        </Button>
      </div>

      {editing !== null && (
        <PackForm pack={editing === "new" ? null : editing} onDone={done} onCancel={() => setEditing(null)} />
      )}

      <AsyncView
        state={state}
        onRetry={state.reload}
        isEmpty={(rows) => rows.length === 0}
        emptyMessage={t("packs.empty")}
      >
        {(rows) => (
          <ul
            aria-label={t("packs.title")}
            className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface"
          >
            {bySchoolLevel(rows).map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setEditing(p)}
                  className={`flex min-h-16 w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ground active:bg-line ${
                    p.is_active ? "" : "text-muted"
                  }`}
                >
                  <span className="flex h-10 min-w-12 shrink-0 items-center justify-center rounded-xl bg-brand-soft px-2 text-sm font-bold text-brand">
                    {p.level}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-bold">{p.name}</span>
                    <span className="block truncate text-sm text-muted">
                      {[p.subjects.join(", "), !p.is_active && t("packs.retired")].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className={`block font-bold tabular-nums ${p.is_active ? "" : "line-through"}`}>
                      {formatMoney(p.price)}
                    </span>
                    <span className="block text-sm text-muted">
                      {t("packs.studentCount", { count: p.student_count })}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </div>
  );
}

/** Packs in school order (1AC → 2BAC), then by name; what's no longer offered goes last. */
function bySchoolLevel(rows: PackDetail[]): PackDetail[] {
  const rank = (level: ClassLevel) => CLASS_LEVELS.indexOf(level);
  return [...rows].sort(
    (a, b) =>
      Number(b.is_active) - Number(a.is_active) || rank(a.level) - rank(b.level) || a.name.localeCompare(b.name),
  );
}

/**
 * Create a pack, or edit one on its own. Its level is fixed once a student has it: changing it
 * then would silently put them on a pack for another level (the server refuses it too).
 */
function PackForm({ pack, onDone, onCancel }: { pack: PackDetail | null; onDone: () => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const create = useMutation(createPack);
  const update = useMutation(updatePack);
  const remove = useMutation(deletePack);

  const [name, setName] = useState(pack?.name ?? "");
  const [level, setLevel] = useState<ClassLevel>(pack?.level ?? CLASS_LEVELS[0]!);
  const [subjects, setSubjects] = useState(pack?.subjects.join(", ") ?? "");
  const [price, setPrice] = useState(pack ? pack.price.replace(/\.0+$/, "") : "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const students = pack?.student_count ?? 0;
  const levelLocked = students > 0;
  // A French keyboard types "450,50"; the API reads decimal points. A string edit, not a parse.
  const normalizedPrice = price.trim().replace(",", ".");
  const subjectList = subjects
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const priceChanged = pack !== null && normalizedPrice !== pack.price.replace(/\.0+$/, "");

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = t("packs.validation.nameRequired");
    if (subjectList.length === 0) next.subjects = t("packs.validation.subjectsRequired");
    if (normalizedPrice === "" || Number.isNaN(Number(normalizedPrice)) || Number(normalizedPrice) < 0) {
      next.price = t("packs.validation.priceInvalid");
    }
    return next;
  }

  async function run(action: () => Promise<unknown>) {
    setFormError(null);
    try {
      await action();
      onDone();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const clientErrors = validate();
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) return;
    const fields = { name: name.trim(), subjects: subjectList, price: normalizedPrice };
    if (pack === null) {
      await run(() => create.mutate({ ...fields, level }));
    } else {
      const body: PackUpdate = level === pack.level ? fields : { ...fields, level };
      await run(() => update.mutate(pack.id, body));
    }
  }

  const pending = create.status === "pending" || update.status === "pending" || remove.status === "pending";

  return (
    <Modal title={t(pack ? "packs.editTitle" : "packs.newTitle")} onClose={onCancel}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        <TextField id="pack-name" label={t("packs.name")} value={name} onChange={setName} error={errors.name} />
        <Select
          id="pack-level"
          label={t("packs.level")}
          value={level}
          onChange={(value) => setLevel(value as ClassLevel)}
          options={CLASS_LEVELS.map((l) => ({ value: l, label: l }))}
          disabled={levelLocked}
          hint={levelLocked ? t("packs.levelLocked", { count: students }) : undefined}
          error={errors.level}
        />
        <TextField
          id="pack-subjects"
          label={t("packs.subjects")}
          value={subjects}
          onChange={setSubjects}
          hint={t("packs.subjectsHint")}
          error={errors.subjects}
        />
        <MoneyField
          id="pack-price"
          label={t("packs.price")}
          value={price}
          onChange={setPrice}
          error={errors.price}
          placeholder="400"
        />
        {/* A price change reaches the students already on the pack, unpaid months included. */}
        {priceChanged && students > 0 && (
          <p className="rounded-xl bg-warn-soft p-3 text-sm text-warn">{t("packs.affects", { count: students })}</p>
        )}
        {formError && <p className="text-sm font-bold text-bad">{formError}</p>}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={create.status === "pending" || update.status === "pending"}>
            {t("common.save")}
          </Button>
        </div>

        {pack && (
          <div className="flex flex-col gap-2 border-t border-line pt-4">
            {/* Retiring keeps the pack for the students on it but stops offering it to new
                ones; deleting is only for a pack nobody has. */}
            <Button
              type="button"
              variant="secondary"
              disabled={pending}
              onClick={() => run(() => update.mutate(pack.id, { is_active: !pack.is_active }))}
            >
              {t(pack.is_active ? "packs.retire" : "packs.restore")}
            </Button>
            {pack.is_active && <p className="text-sm text-muted">{t("packs.retireHint")}</p>}
            {students === 0 && (
              <Button
                type="button"
                variant="ghost"
                disabled={pending}
                onClick={() => run(() => remove.mutate(pack.id))}
                className="text-bad"
              >
                {t("packs.delete")}
              </Button>
            )}
          </div>
        )}
      </form>
    </Modal>
  );
}
