import { Field } from "./Field";
import { inputClass } from "./inputClass";
import type { FieldProps } from "./TextField";

/** Native date picker; value is a `YYYY-MM-DD` string. */
export function DateField({ id, label, value, onChange, hint, error, required, disabled }: FieldProps & { disabled?: boolean }) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        disabled={disabled}
        className={`${inputClass(!!error)} disabled:cursor-not-allowed disabled:border-dashed disabled:bg-ground disabled:text-muted`}
      />
    </Field>
  );
}
