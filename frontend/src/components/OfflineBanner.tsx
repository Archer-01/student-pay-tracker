import { useTranslation } from "react-i18next";
import { useConnectivity } from "../lib/connectivity";

/**
 * Says, while offline, that what's on screen can't be changed and how old it is. Read-only is
 * stated here once; the buttons that would save something are switched off where they are.
 */
export function OfflineBanner() {
  const { t, i18n } = useTranslation();
  const state = useConnectivity();
  if (state.mode === "live") return null;

  let text = t("offline.none");
  if (state.mode === "stored") {
    const saved = new Date(state.savedAt);
    text = t("offline.stored", {
      date: new Intl.DateTimeFormat(i18n.language, { day: "numeric", month: "short" }).format(saved),
      time: new Intl.DateTimeFormat(i18n.language, { hour: "numeric", minute: "2-digit" }).format(saved),
    });
  }
  return (
    <p
      role="status"
      className="sticky top-0 z-30 flex items-center justify-center gap-2 bg-ink px-4 pb-2 pt-[calc(0.5rem+env(safe-area-inset-top))] text-center text-sm font-bold text-ground"
    >
      {text}
    </p>
  );
}
