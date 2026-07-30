import { Field } from "./Field";
import { inputClass } from "./inputClass";
import type { FieldProps } from "./TextField";

/**
 * Money input. Deliberately string-preserving: the raw text goes straight to `onChange` and on to the
 * API — never parsed to a JS number, since money is a decimal string end to end.
 */
export function MoneyField({ id, label, value, onChange, hint, error, placeholder = "300.00", required }: FieldProps) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className={inputClass(!!error)}
      />
    </Field>
  );
}
