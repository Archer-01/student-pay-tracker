import { Field } from "./Field";
import { inputClass } from "./inputClass";
import type { FieldProps } from "./TextField";

/**
 * A `TextField` with `type="password"`. Separate rather than a `type` prop on TextField because
 * it also carries the autocomplete hint password managers need — the behaviour differs, not just
 * the markup.
 */
export function PasswordField({
  id,
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  required,
  autoComplete = "current-password",
}: FieldProps & { autoComplete?: string }) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        autoComplete={autoComplete}
        className={inputClass(!!error)}
      />
    </Field>
  );
}
