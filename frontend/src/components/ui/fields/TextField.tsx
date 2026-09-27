import { Field } from "./Field";
import { inputClass } from "./inputClass";

export type FieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  placeholder?: string;
  required?: boolean;
  /** Passed straight through to the input. Password managers need it on the *username* field as
      well as the password one to reliably offer save and autofill. */
  autoComplete?: string;
};

export function TextField({ id, label, value, onChange, hint, error, placeholder, required, autoComplete }: FieldProps) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="text"
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
