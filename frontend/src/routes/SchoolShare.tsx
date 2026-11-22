import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { getSchoolShare, handOverAllShare, markShareHandedOver, unmarkShareHandedOver } from "../api/endpoints";
import type { SchoolShare as Share, ShareMonth } from "../api/types";
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
 * settled shows as what is missing; marking the month again records the full share. With two or
 * more months outstanding, the card adds their total and a way to mark them all at once (for
 * months already handed over in cash), which asks first.
 */
export function SchoolShare() {
  const { t } = useTranslation();
  const readOnly = useReadOnly();
  // A payment taken anywhere can change a month's share.
  const paymentsVersion = usePaymentsVersion();
  const state = useApi(() => getSchoolShare(), [paymentsVersion]);
  const [open, setOpen] = useState<ShareMonth | null>(null);
  const [catchingUp, setCatchingUp] = useState<Share | null>(null);

  const done = () => {
    setOpen(null);
    setCatchingUp(null);
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
                  {data.outstanding_months >= 2 && (
                    <div className="mt-1 flex flex-col gap-1">
                      <p className="font-bold text-warn">
                        {t("schoolShare.total", {
                          amount: formatMoney(data.outstanding),
                          count: data.outstanding_months,
                        })}
                      </p>
                      <button
                        type="button"
                        onClick={() => setCatchingUp(data)}
                        disabled={readOnly}
                        className="min-h-11 self-start font-bold text-warn underline disabled:opacity-50"
                      >
                        {t("schoolShare.markAll")}
                      </button>
                    </div>
                  )}
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
                        <span className="block whitespace-nowrap font-bold">{formatMonthTitle(ym(m))}</span>
                        <span className="block text-sm text-muted">
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
      {catchingUp && <CatchUpSheet share={catchingUp} onClose={() => setCatchingUp(null)} onDone={done} />}
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
  const date = useHandedOn();
  const [error, setError] = useState<string | null>(null);
  const title = formatMonthTitle(ym(month));
  const handedOn = date.value;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const invalid = date.problem();
    if (invalid) return setError(invalid);
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
            <HandedOnField date={date} />
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

/** Catch up: every month still to hand over, marked as handed over on one day, said in full first. */
function CatchUpSheet({ share, onClose, onDone }: { share: Share; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const markAll = useMutation(handOverAllShare);
  const date = useHandedOn();
  const [error, setError] = useState<string | null>(null);
  const counted = { count: share.outstanding_months, amount: formatMoney(share.outstanding) };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const invalid = date.problem();
    if (invalid) return setError(invalid);
    try {
      await markAll.mutate(date.value);
      onDone();
    } catch (err) {
      setError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={t("schoolShare.markAll")} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <p>{t("schoolShare.markAllText", counted)}</p>
        <HandedOnField date={date} />
        {error && <p className="text-sm font-bold text-bad">{error}</p>}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" pending={markAll.status === "pending"} className="min-h-12">
            {t("schoolShare.markAllButton", counted)}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** The day a share was handed over: today, or another day (never in the future). */
function useHandedOn() {
  const { t } = useTranslation();
  const [today, setToday] = useState(true);
  const [other, setOther] = useState("");
  const value = today ? todayIso() : other;
  return {
    today,
    setToday,
    other,
    setOther,
    value,
    problem: () =>
      !value
        ? t("schoolShare.validation.dateRequired")
        : value > todayIso()
          ? t("schoolShare.validation.dateFuture")
          : null,
  };
}

function HandedOnField({ date }: { date: ReturnType<typeof useHandedOn> }) {
  const { t } = useTranslation();
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-sm font-bold">{t("schoolShare.handedDate")}</legend>
      <div className="flex flex-wrap gap-2">
        <Chip name="handed_on" checked={date.today} onChange={() => date.setToday(true)}>
          {t("pay.today")}
        </Chip>
        <Chip name="handed_on" checked={!date.today} onChange={() => date.setToday(false)}>
          {t("pay.otherDate")}
        </Chip>
      </div>
      {!date.today && (
        <DateField id="share-handed-on" label={t("schoolShare.handedDate")} value={date.other} onChange={date.setOther} />
      )}
    </fieldset>
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
