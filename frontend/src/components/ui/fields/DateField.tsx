import { Field } from "./Field";
import { inputClass } from "./inputClass";
import type { FieldProps } from "./TextField";

/** Native date picker; value is a `YYYY-MM-DD` string. */
export function DateField({ id, label, value, onChange, hint, error, required }: FieldProps) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className={inputClass(!!error)}
      />
    </Field>
  );
}
