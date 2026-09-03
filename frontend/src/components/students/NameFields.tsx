import { useTranslation } from "react-i18next";
import { TextField } from "../ui";

type Props = {
  firstName: string;
  onFirstName: (value: string) => void;
  lastName: string;
  onLastName: (value: string) => void;
  errors?: Record<string, string>;
};

/**
 * First and last name, shared by enrolment and editing.
 *
 * The surname is optional on purpose: a compound given name with no family name ("Fatima Zahra")
 * is a real case, and forcing a split invents a surname that doesn't exist.
 */
export function NameFields({ firstName, onFirstName, lastName, onLastName, errors = {} }: Props) {
  const { t } = useTranslation();
  return (
    <>
      <TextField
        id="student-first-name"
        label={t("student.firstName")}
        value={firstName}
        onChange={onFirstName}
        error={errors.first_name}
        required
      />
      <TextField
        id="student-last-name"
        label={t("student.lastName")}
        value={lastName}
        onChange={onLastName}
        hint={t("student.lastNameHint")}
        error={errors.last_name}
      />
    </>
  );
}
