import { Field } from "./Field";
import { inputClass } from "./inputClass";

/** A few lines of free text, styled like the other fields. `maxLength` matches the server's. */
export function TextAreaField({
  id,
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  maxLength,
  rows = 3,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  placeholder?: string;
  maxLength?: number;
  rows?: number;
}) {
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        rows={rows}
        className={`${inputClass(!!error)} resize-y leading-snug`}
      />
    </Field>
  );
}
