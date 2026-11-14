import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button, Card, PasswordField, TextField } from "../components/ui";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { Logo } from "../components/Logo";
import { resolveErrorMessage } from "../lib/errors";
import { useAuth } from "../lib/authContext";

/**
 * The only screen reachable while signed out.
 *
 * It renders outside `Layout` deliberately: the nav shell links to six pages that would all
 * bounce straight back here, which is a worse experience than not offering them.
 *
 * Note the fields are validated on submit rather than with `required`. A `required` input makes
 * the browser block submission before any handler runs, which would make these messages
 * unreachable — the same trap `frontend/CLAUDE.md` records from the enrolment form.
 */
export function Login() {
  const { t } = useTranslation();
  const { signIn, sessionExpired } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const nextErrors = {
      username: username.trim() ? undefined : t("auth.usernameRequired"),
      password: password ? undefined : t("auth.passwordRequired"),
    };
    setErrors(nextErrors);
    if (nextErrors.username || nextErrors.password) return;

    setFormError(null);
    setPending(true);
    try {
      await signIn(username.trim(), password);
      // No redirect here: `App` swaps the whole tree once `user` is set, so navigating would
      // race that re-render.
    } catch (err) {
      setFormError(resolveErrorMessage(err, t));
      // Keep the username — getting the password wrong shouldn't cost you both fields.
      setPassword("");
    } finally {
      setPending(false);
    }
  }

  return (
    // `dvh`, not `vh`/`min-h-screen`: on a phone 100vh is the height with the address bar
    // hidden, so while it shows the page is taller than the screen and scrolls for nothing.
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 pb-[calc(2.5rem+env(safe-area-inset-bottom))] pt-[calc(2.5rem+env(safe-area-inset-top))]">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-between">
          {/* The page's heading: the card itself has no title, since "Se connecter" on the
              button already says what it is for. */}
          <h1 className="flex items-center gap-2.5 font-display text-2xl font-extrabold tracking-tight text-brand">
            <Logo className="h-10 w-10" />
            {t("app.title")}
          </h1>
          <span className="flex items-center gap-2">
            <LanguageSwitcher />
          </span>
        </div>

        <Card>
          {/* Named for screen readers, which announce a form by its label. */}
          <form onSubmit={handleSubmit} aria-label={t("auth.title")} className="flex flex-col gap-4" noValidate>

            {sessionExpired && !formError && (
              <p
                role="status"
                className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200"
              >
                {t("auth.expired")}
              </p>
            )}

            <TextField
              id="username"
              label={t("auth.username")}
              value={username}
              onChange={setUsername}
              error={errors.username}
              autoComplete="username"
            />
            <PasswordField
              id="password"
              label={t("auth.password")}
              value={password}
              onChange={setPassword}
              error={errors.password}
              autoComplete="current-password"
            />

            {formError && (
              <p
                role="alert"
                className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300"
              >
                {formError}
              </p>
            )}

            <Button type="submit" pending={pending}>
              {t("auth.submit")}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
