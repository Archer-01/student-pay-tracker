import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createOffering, getPackGrid, updateOffering, updatePack } from "../api/endpoints";
import type { ClassLevel, PackGridCell, PackGridRow } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { fieldErrors, resolveErrorMessage } from "../lib/errors";
import { formatMoney } from "../lib/money";
import { CLASS_LEVELS } from "../lib/classes";
import {
  AsyncView,
  Button,
  Card,
  Modal,
  MoneyField,
  PageHeader,
  TextField,
} from "../components/ui";

/**
 * The price list, rendered as a matrix: one row per offering, one column per level.
 *
 * Deliberately not one form per pack — with four offerings across six levels that is 24 screens
 * for a single round of price changes, and the subject lists of an offering's level-variants
 * would drift apart. Editing a *cell* changes one price; editing a *row* (name, subjects) hits
 * every level at once.
 */
export function PacksGrid() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<{ row: PackGridRow; cell: PackGridCell } | null>(null);
  const [editingOffering, setEditingOffering] = useState<PackGridRow | null>(null);

  const state = useApi(() => getPackGrid(), []);

  return (
    <div>
      <PageHeader
        title={t("pages.packs")}
        actions={<Button onClick={() => setCreating(true)}>{t("packs.newOffering")}</Button>}
      />

      {creating && (
        <NewOfferingModal
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            state.reload();
          }}
        />
      )}
      {editingOffering && (
        <EditOfferingModal
          row={editingOffering}
          onClose={() => setEditingOffering(null)}
          onSaved={() => {
            setEditingOffering(null);
            state.reload();
          }}
        />
      )}
      {editing && (
        <EditCellModal
          row={editing.row}
          cell={editing.cell}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            state.reload();
          }}
        />
      )}

      <AsyncView
        state={state}
        onRetry={state.reload}
        isEmpty={(grid) => grid.rows.length === 0}
        emptyMessage={t("packs.empty")}
      >
        {(grid) => (
          <>
            <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">{t("packs.gridHint")}</p>
            <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800/60">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-slate-500 dark:text-slate-400">
                      {t("packs.offering")}
                    </th>
                    {grid.levels.map((level) => (
                      <th
                        key={level}
                        className="px-4 py-2 text-right font-medium text-slate-500 dark:text-slate-400"
                      >
                        {level}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.rows.map((row) => (
                    <tr
                      key={row.name}
                      className="border-t border-slate-200 dark:border-slate-800"
                    >
                      <td className="px-4 py-2">
                        {/* Editing the row header edits the offering: its name and subjects,
                            across every level. Only prices are per-cell. */}
                        <button
                          onClick={() => setEditingOffering(row)}
                          className="text-left hover:underline"
                          title={t("packs.editOffering")}
                        >
                          <div className="font-medium text-slate-900 dark:text-slate-100">
                            {row.name}
                          </div>
                          <div className="text-xs text-slate-400 dark:text-slate-500">
                            {row.subjects.join(", ")}
                          </div>
                        </button>
                      </td>
                      {row.cells.map((cell) => (
                        <td key={cell.level} className="px-2 py-2 text-right">
                          <PriceCell
                            cell={cell}
                            onEdit={() => setEditing({ row, cell })}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </AsyncView>
    </div>
  );
}

/** One grid cell. Shows the price, how many students are on it, and its inactive state. */
function PriceCell({ cell, onEdit }: { cell: PackGridCell; onEdit: () => void }) {
  const { t } = useTranslation();

  if (cell.pack_id === null || cell.price === null) {
    return (
      <span className="text-xs text-slate-300 dark:text-slate-600">{t("packs.notOffered")}</span>
    );
  }
  return (
    <button
      onClick={onEdit}
      className="w-full rounded px-2 py-1 text-right hover:bg-indigo-50 dark:hover:bg-indigo-950"
    >
      <span
        className={
          cell.is_active
            ? "font-medium text-slate-900 dark:text-slate-100"
            : "font-medium text-slate-400 line-through dark:text-slate-500"
        }
      >
        {formatMoney(cell.price)}
      </span>
      {/* The blast radius of a price change, visible before you click. */}
      {cell.student_count > 0 && (
        <span className="block text-xs text-slate-400 dark:text-slate-500">
          {cell.student_count} {t("packs.students")}
        </span>
      )}
    </button>
  );
}

function EditCellModal({
  row,
  cell,
  onClose,
  onSaved,
}: {
  row: PackGridRow;
  cell: PackGridCell;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const save = useMutation(updatePack);

  const [price, setPrice] = useState(cell.price ?? "");
  const [isActive, setIsActive] = useState(cell.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (cell.pack_id === null) return;
    try {
      await save.mutate(cell.pack_id, { price, is_active: isActive });
      onSaved();
    } catch (err) {
      setError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal
      title={t("packs.editCellTitle", { offering: row.name, level: cell.level })}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <MoneyField
          id="pack-price"
          label={t("packs.editPrice")}
          value={String(price)}
          onChange={setPrice}
          required
        />

        {/* A price change takes effect immediately, including for months not yet paid — so say
            how many students it moves before they click. */}
        {cell.student_count > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            {t("packs.affects", { count: cell.student_count })}
          </p>
        )}

        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
          />
          {t("packs.offered")}
        </label>

        {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={save.status === "pending"}>
            {t("packs.save")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function NewOfferingModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useTranslation();
  const create = useMutation(createOffering);
  const [name, setName] = useState("");
  const [subjects, setSubjects] = useState("");
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const subjectList = subjects
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    // Only levels with a price become packs — an empty cell means "not offered here".
    const priced = Object.entries(prices).filter(([, value]) => value.trim() !== "");

    const next: Record<string, string> = {};
    if (!name.trim()) next.name = t("packs.validation.nameRequired");
    if (subjectList.length === 0) next.subjects = t("packs.validation.subjectsRequired");
    if (priced.length === 0) next.prices = t("packs.validation.pricesRequired");
    if (Object.keys(next).length > 0) {
      setErrors(next);
      return;
    }
    setErrors({});

    try {
      await create.mutate({
        name: name.trim(),
        subjects: subjectList,
        prices: Object.fromEntries(priced) as Record<ClassLevel, string>,
      });
      onCreated();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={t("packs.newOfferingTitle")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <TextField
          id="offering-name"
          label={t("packs.offering")}
          value={name}
          onChange={setName}
          error={errors.name}
          required
        />
        <TextField
          id="offering-subjects"
          label={t("packs.subjects")}
          value={subjects}
          onChange={setSubjects}
          hint={t("packs.subjectsHint")}
          error={errors.subjects}
          required
        />
        <Card className="space-y-2">
          <p className="text-xs text-slate-500 dark:text-slate-400">{t("packs.pricesHint")}</p>
          {CLASS_LEVELS.map((level) => (
            <div key={level} className="flex items-center gap-3">
              <span className="w-14 text-sm text-slate-600 dark:text-slate-300">{level}</span>
              <div className="flex-1">
                <MoneyField
                  id={`offering-price-${level}`}
                  label=""
                  value={prices[level] ?? ""}
                  onChange={(value) => setPrices((p) => ({ ...p, [level]: value }))}
                />
              </div>
            </div>
          ))}
          {errors.prices && (
            <p className="text-xs text-rose-600 dark:text-rose-400">{errors.prices}</p>
          )}
        </Card>
        {formError && <p className="text-sm text-rose-600 dark:text-rose-400">{formError}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={create.status === "pending"}>
            {t("packs.newOffering")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function EditOfferingModal({
  row,
  onClose,
  onSaved,
}: {
  row: PackGridRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const save = useMutation(updateOffering);
  const [name, setName] = useState(row.name);
  const [subjects, setSubjects] = useState(row.subjects.join(", "));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const subjectList = subjects
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = t("packs.validation.nameRequired");
    if (subjectList.length === 0) next.subjects = t("packs.validation.subjectsRequired");
    if (Object.keys(next).length > 0) {
      setErrors(next);
      return;
    }
    setErrors({});
    try {
      // One call updates every level-variant, which is what stops their subject lists diverging.
      await save.mutate(row.name, { name: name.trim(), subjects: subjectList });
      onSaved();
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      else setFormError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={t("packs.editOfferingTitle", { name: row.name })} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {t("packs.appliesToAllLevels")}
        </p>
        <TextField
          id="offering-edit-name"
          label={t("packs.offering")}
          value={name}
          onChange={setName}
          error={errors.name}
          required
        />
        <TextField
          id="offering-edit-subjects"
          label={t("packs.subjects")}
          value={subjects}
          onChange={setSubjects}
          hint={t("packs.subjectsHint")}
          error={errors.subjects}
          required
        />
        {formError && <p className="text-sm text-rose-600 dark:text-rose-400">{formError}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={save.status === "pending"}>
            {t("packs.save")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
