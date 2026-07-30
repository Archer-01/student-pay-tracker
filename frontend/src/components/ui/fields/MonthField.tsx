import { Field } from "./Field";
import { inputClass } from "./inputClass";
import type { FieldProps } from "./TextField";

/** Native month picker; value is a `YYYY-MM` string (matches the payment `for_month` contract). */
export function MonthField({ id, label, value, onChange, hint, error, required }: FieldProps) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="month"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className={inputClass(!!error)}
      />
    </Field>
  );
}
