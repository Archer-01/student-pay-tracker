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
};

export function TextField({ id, label, value, onChange, hint, error, placeholder, required }: FieldProps) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className={inputClass(!!error)}
      />
    </Field>
  );
}
