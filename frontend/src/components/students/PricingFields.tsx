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
  errors = {},
}: Props) {
  const { t } = useTranslation();
  // Retired packs can't be assigned; they stay visible only on students already on them.
  const packs = useApi(() => listPacks({ active: true }), []);

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
        onChange={onPackId}
        options={[{ value: "", label: t("student.noPack") }, ...options]}
        hint={selected ? t("student.packPriceHint", { price: formatMoney(selected.price) }) : undefined}
        error={errors.pack_id}
      />
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
