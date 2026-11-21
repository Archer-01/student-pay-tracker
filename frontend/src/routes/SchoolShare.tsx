import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { getSchoolShare, markShareHandedOver, unmarkShareHandedOver } from "../api/endpoints";
import type { ShareMonth } from "../api/types";
import { useApi } from "../lib/useApi";
import { useMutation } from "../lib/useMutation";
import { usePaymentsVersion } from "../lib/paymentSheetContext";
import { useReadOnly } from "../lib/connectivity";
import { resolveErrorMessage } from "../lib/errors";
import { formatMoney, formatPercent } from "../lib/money";
import { formatDate, formatDayMonth, formatMonthTitle, todayIso } from "../lib/dates";
import { ReportTabs } from "../components/ReportTabs";
import { Chip } from "../components/students/Chip";
import { AsyncView, Button, DateField, Modal } from "../components/ui";
import { ChevronRightIcon } from "../components/icons";

const ym = (m: ShareMonth) => `${m.year}-${String(m.month).padStart(2, "0")}`;

/**
 * Bilan › École: the school's share of each month and whether it was handed over. Leads with the
 * latest month still to hand over and the button that settles it; below, every month in words
 * ("Remis le 3 nov.", "Il manque 50 DH", "À remettre"). A payment recorded after a month was
 * settled shows as what is missing; marking the month again records the full share.
 */
export function SchoolShare() {
  const { t } = useTranslation();
  const readOnly = useReadOnly();
  // A payment taken anywhere can change a month's share.
  const paymentsVersion = usePaymentsVersion();
  const state = useApi(() => getSchoolShare(), [paymentsVersion]);
  const [open, setOpen] = useState<ShareMonth | null>(null);

  const done = () => {
    setOpen(null);
    state.reload();
  };

  return (
    <div className="flex flex-col gap-5">
      <ReportTabs />
      <AsyncView state={state} onRetry={state.reload}>
        {(data) => {
          if (Number(data.percent) <= 0) return <p className="text-muted">{t("schoolShare.off")}</p>;
          if (data.months.length === 0) return <p className="text-muted">{t("schoolShare.empty")}</p>;
          const running = data.months.find((m) => m.status === "running");
          const past = data.months.filter((m) => m.status !== "running");
          const next = past.find((m) => m.status === "due" || m.status === "short");
          return (
            <>
              <header className="flex flex-col gap-1">
                <h1 className="font-display text-3xl font-extrabold tracking-tight">{t("schoolShare.title")}</h1>
                <p className="text-muted">{t("schoolShare.intro", { percent: formatPercent(data.percent) })}</p>
              </header>

              {next && (
                <section
                  aria-label={t("schoolShare.toHandOver")}
                  className="flex flex-col gap-2 rounded-2xl bg-warn-soft p-4"
                >
                  <p className="text-sm font-bold text-warn">{formatMonthTitle(ym(next))}</p>
                  <p className="font-display text-2xl font-extrabold tracking-tight text-warn">
                    {next.status === "short"
                      ? t("schoolShare.shortBy", { amount: formatMoney(next.remaining) })
                      : t("schoolShare.toHandOverAmount", { amount: formatMoney(next.remaining) })}
                  </p>
                  <Button onClick={() => setOpen(next)} disabled={readOnly} className="min-h-12 sm:self-start">
                    {t("schoolShare.mark")}
                  </Button>
                </section>
              )}

              {running && (
                <p className="rounded-2xl border border-line bg-surface p-4 text-muted">
                  <span className="font-bold text-ink">{formatMonthTitle(ym(running))}</span>
                  {" · "}
                  {t("schoolShare.running", { amount: formatMoney(running.due) })}
                </p>
              )}

              <ul
                aria-label={t("schoolShare.months")}
                className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface"
              >
                {past.map((m) => (
                  <li key={ym(m)}>
                    <button
                      type="button"
                      onClick={() => setOpen(m)}
                      disabled={m.status === "nothing"}
                      aria-label={formatMonthTitle(ym(m))}
                      className="flex min-h-16 w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-ground active:bg-line disabled:cursor-default disabled:hover:bg-transparent"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block font-bold">{formatMonthTitle(ym(m))}</span>
                        <span className="block truncate text-sm text-muted">
                          {t("schoolShare.collected", { collected: formatMoney(m.collected), due: formatMoney(m.due) })}
                        </span>
                      </span>
                      <StatusPill month={m} />
                      {m.status !== "nothing" && <ChevronRightIcon className="h-5 w-5 shrink-0 text-muted" />}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          );
        }}
      </AsyncView>

      {open && <MonthSheet month={open} readOnly={readOnly} onClose={() => setOpen(null)} onDone={done} />}
    </div>
  );
}

function StatusPill({ month }: { month: ShareMonth }) {
  const { t } = useTranslation();
  const [tone, label] =
    month.status === "handed"
      ? ["bg-ok-soft text-ok", t("schoolShare.handedOn", { date: formatDayMonth(month.handed_on ?? "") })]
      : month.status === "short"
        ? ["bg-warn-soft text-warn", t("schoolShare.shortBy", { amount: formatMoney(month.remaining) })]
        : month.status === "due"
          ? ["bg-warn-soft text-warn", t("schoolShare.toHandOver")]
          : ["bg-off-soft text-off", t("schoolShare.nothing")];
  return <span className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1 text-sm font-bold ${tone}`}>{label}</span>;
}

/**
 * One month: mark it handed over (today by default, or another day), or, once handed over, see
 * when and undo it. Undoing asks first.
 */
function MonthSheet({
  month,
  readOnly,
  onClose,
  onDone,
}: {
  month: ShareMonth;
  readOnly: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const mark = useMutation(markShareHandedOver);
  const unmark = useMutation(unmarkShareHandedOver);
  const [mode, setMode] = useState<"view" | "mark" | "undo">(month.status === "handed" ? "view" : "mark");
  const [today, setToday] = useState(true);
  const [otherDate, setOtherDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const title = formatMonthTitle(ym(month));
  const handedOn = today ? todayIso() : otherDate;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!handedOn) return setError(t("schoolShare.validation.dateRequired"));
    if (handedOn > todayIso()) return setError(t("schoolShare.validation.dateFuture"));
    try {
      await mark.mutate(month.year, month.month, handedOn);
      onDone();
    } catch (err) {
      setError(resolveErrorMessage(err, t));
    }
  }

  async function undo() {
    setError(null);
    try {
      await unmark.mutate(month.year, month.month);
      onDone();
    } catch (err) {
      setError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <dl className="divide-y divide-line rounded-2xl border border-line">
          <Row label={t("schoolShare.collectedLabel")}>{formatMoney(month.collected)}</Row>
          <Row label={t("schoolShare.dueLabel")}>{formatMoney(month.due)}</Row>
          {month.handed_on && (
            <Row label={t("schoolShare.handedLabel")}>
              {formatMoney(month.handed_amount ?? "0")}
              <span className="block text-sm font-normal text-muted">{formatDate(month.handed_on)}</span>
            </Row>
          )}
        </dl>

        {mode === "mark" && !readOnly && (
          <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-sm font-bold">{t("schoolShare.handedDate")}</legend>
              <div className="flex flex-wrap gap-2">
                <Chip name="handed_on" checked={today} onChange={() => setToday(true)}>
                  {t("pay.today")}
                </Chip>
                <Chip name="handed_on" checked={!today} onChange={() => setToday(false)}>
                  {t("pay.otherDate")}
                </Chip>
              </div>
              {!today && (
                <DateField id="share-handed-on" label={t("schoolShare.handedDate")} value={otherDate} onChange={setOtherDate} />
              )}
            </fieldset>
            {error && <p className="text-sm font-bold text-bad">{error}</p>}
            <Button type="submit" pending={mark.status === "pending"} className="min-h-12 text-lg">
              {t("schoolShare.mark")}
            </Button>
          </form>
        )}

        {mode === "view" && !readOnly && (
          <div className="flex flex-col gap-1">
            <Button variant="secondary" onClick={() => setMode("mark")}>
              {t("schoolShare.changeDate")}
            </Button>
            <button
              type="button"
              onClick={() => setMode("undo")}
              className="min-h-11 rounded-xl px-4 font-bold text-bad transition hover:bg-bad-soft active:scale-[0.97]"
            >
              {t("schoolShare.undo")}
            </button>
          </div>
        )}

        {mode === "undo" && (
          <div className="flex flex-col gap-3 rounded-2xl bg-bad-soft p-4">
            <p className="font-bold text-bad">{t("schoolShare.undoConfirm", { month: title })}</p>
            {error && <p className="text-sm font-bold text-bad">{error}</p>}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button variant="ghost" onClick={() => setMode("view")}>
                {t("common.cancel")}
              </Button>
              <Button variant="danger" pending={unmark.status === "pending"} onClick={() => void undo()}>
                {t("schoolShare.undoButton")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 py-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-bold">{children}</dd>
    </div>
  );
}
