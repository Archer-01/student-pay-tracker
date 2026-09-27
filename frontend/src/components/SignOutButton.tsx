import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/authContext";

/**
 * Sign out, with the signed-in name as its tooltip — there are two accounts on shared machines,
 * so "who am I currently?" is a real question and the title attribute answers it without
 * spending nav width on a name.
 */
export function SignOutButton() {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();

  if (!user) return null;

  return (
    <button
      type="button"
      onClick={() => void signOut()}
      aria-label={t("auth.signOut")}
      title={t("auth.signedInAs", { name: user.display_name })}
      className="rounded-md border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
    >
      <svg
        className="h-4 w-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
        <polyline points="16 17 21 12 16 7" />
        <line x1="21" y1="12" x2="9" y2="12" />
      </svg>
    </button>
  );
}
