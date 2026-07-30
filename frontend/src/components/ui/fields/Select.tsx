import { Field } from "./Field";
import { inputClass } from "./inputClass";

export type SelectOption = { value: string; label: string };

export function Select({
  id,
  label,
  value,
  onChange,
  options,
  hint,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  hint?: string;
  error?: string;
}) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={inputClass(!!error)}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
