import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listPacks } from "../../api/endpoints";
import { useApi } from "../../lib/useApi";
import { formatMoney } from "../../lib/money";
import { MoneyField, Select, TextField } from "../ui";

type Props = {
  packId: string;
  onPackId: (value: string) => void;
  customPrice: string;
  onCustomPrice: (value: string) => void;
  priceNote: string;
  onPriceNote: (value: string) => void;
  /** The student's class level, used to sort the most likely packs to the top. */
  classLevel?: string | null;
  /**
   * Enrolment only: until the teacher picks a pack themselves, choose the one pack sold at the
   * class's level (and none when there are several, or none). Editing never sets this, so an
   * existing student's pack only changes when the teacher changes it.
   */
  pickFromClass?: boolean;
  errors?: Record<string, string>;
};

/**
 * Pack + optional agreed price + why. Shared by enrolment and editing so a student's price is
 * set in one shape wherever you are.
 *
 * A student pays their pack's price unless an agreed price is filled in — that field is the only
 * per-student number, and the note beside it records the arrangement.
 */
export function PricingFields({
  packId,
  onPackId,
  customPrice,
  onCustomPrice,
  priceNote,
  onPriceNote,
  classLevel,
  pickFromClass = false,
  errors = {},
}: Props) {
  const { t } = useTranslation();
  // Retired packs can't be assigned; they stay visible only on students already on them.
  const packs = useApi(() => listPacks({ active: true }), []);

  // Once the teacher touches the pack, it is theirs: never picked over again, even "no pack".
  const [teacherChose, setTeacherChose] = useState(false);
  // The pack the class suggests ("" for none), or null while nothing should be picked. Until the
  // teacher chooses, the pack follows the class, so changing class can't leave a stale guess.
  const atLevel = (packs.data ?? []).filter((p) => classLevel && p.level === classLevel);
  const suggested =
    pickFromClass && !teacherChose && packs.status === "success" ? (atLevel.length === 1 ? String(atLevel[0].id) : "") : null;
  useEffect(() => {
    // Classes and packs both load after the form opens (and a class can come preset from its
    // page), so this runs when either lands, not only when the class is changed.
    if (suggested !== null && packId !== suggested) onPackId(suggested);
  }, [suggested, packId, onPackId]);
  const pickedFromClass = !!suggested && packId === suggested;

  const options = (packs.data ?? [])
    .slice()
    .sort((a, b) => {
      const rank = (level: string) => (classLevel && level === classLevel ? 0 : 1);
      return rank(a.level) - rank(b.level) || a.name.localeCompare(b.name);
    })
    .map((p) => ({
      value: String(p.id),
      label: `${p.name} · ${p.level} — ${formatMoney(p.price)}`,
    }));

  const selected = (packs.data ?? []).find((p) => String(p.id) === packId);
  // Advisory only. A repeating student, or one sitting with a higher group, is a real case —
  // the backend allows it, so the UI warns rather than blocks.
  const mismatch = selected && classLevel && selected.level !== classLevel;

  return (
    <>
      <Select
        id="student-pack"
        label={t("student.pack")}
        value={packId}
        onChange={(value) => {
          setTeacherChose(true);
          onPackId(value);
        }}
        options={[{ value: "", label: t("student.noPack") }, ...options]}
        hint={selected ? t("student.packPriceHint", { price: formatMoney(selected.price) }) : undefined}
        error={errors.pack_id}
      />
      {pickedFromClass && <p className="-mt-2 text-sm text-muted">{t("student.packFromClass")}</p>}
      {mismatch && selected && (
        <p className="-mt-2 text-xs text-amber-700 dark:text-amber-400">
          {t("student.levelMismatch", { packLevel: selected.level, classLevel })}
        </p>
      )}
      <MoneyField
        id="student-custom-price"
        label={t("student.customPrice")}
        value={customPrice}
        onChange={onCustomPrice}
        hint={t("student.customPriceHint")}
        error={errors.custom_price}
      />
      {customPrice.trim() !== "" && (
        <TextField
          id="student-price-note"
          label={t("student.priceNote")}
          value={priceNote}
          onChange={onPriceNote}
          hint={t("student.priceNoteHint")}
          error={errors.price_note}
        />
      )}
    </>
  );
}
