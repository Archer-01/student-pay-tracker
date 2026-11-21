import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-4 py-20 text-center">
      <p className="font-display text-xl font-bold text-ink">{t("notFound.title")}</p>
      <Link
        to="/"
        className="flex min-h-12 items-center justify-center rounded-xl bg-brand px-5 font-bold text-brand-ink hover:opacity-90"
      >
        {t("notFound.home")}
      </Link>
    </div>
  );
}
