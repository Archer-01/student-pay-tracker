import { useTranslation } from "react-i18next";
import { Button } from "./Button";

/**
 * A question asked in place before a save, never a browser pop-up: the form's own buttons give
 * way to it until it's answered. Amber, not red: nothing is lost, it only checks a choice that
 * has consequences (a price of 0, a corrected join date). Each message is one sentence.
 */
export function ConfirmBox({
  messages,
  onConfirm,
  onCancel,
  pending,
  confirmLabel,
}: {
  messages: string[];
  /** What « oui » does, when not a save (« Oui, inscrire »). */
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-warn-soft p-4" role="group" aria-live="polite">
      {messages.map((message) => (
        <p key={message} className="font-bold text-ink">
          {message}
        </p>
      ))}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {/* type="button": inside a form, a plain button submits it, and would ask again. Not
            « Annuler »: next to a form whose own « Annuler » closes it, this one only goes back. */}
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.noGoBack")}
        </Button>
        <Button type="button" pending={pending} onClick={onConfirm} className="min-h-12">
          {confirmLabel ?? t("common.yesSave")}
        </Button>
      </div>
    </div>
  );
}
