import { useEffect, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { deletePayment, getLedger, getStudent, listPeriods } from "../api/endpoints";
import { downloadFile } from "../api/client";
import type { EnrollmentPeriod, LedgerOut, StudentDetailOut } from "../api/types";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate, formatMonthInSentence, formatMonthTitle } from "../lib/dates";
import { classLabel } from "../lib/classes";
import { slugify } from "../lib/slug";
import { resolveErrorMessage } from "../lib/errors";
import { payableMonths } from "../lib/paymentDefaults";
import { monthTiles, schoolYearStart, schoolYears, type MonthTile } from "../lib/schoolYear";
import { usePaymentSheet } from "../lib/paymentSheetContext";
import { useReadOnly } from "../lib/connectivity";
import { useFlashOnChange } from "../lib/useFlashOnChange";
import { useMutation } from "../lib/useMutation";
import { CreateOverrideForm } from "../components/students/CreateOverrideForm";
import { EditStudentForm } from "../components/students/EditStudentForm";
import { AttendanceForm } from "../components/students/AttendanceForm";
import { EditPaymentForm } from "../components/students/EditPaymentForm";
import { NoteSheet } from "../components/students/NoteSheet";
import { AsyncView, Button, Modal } from "../components/ui";
import { Avatar, PunctualityPill } from "../components/people";
import {
  CalendarIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  LeaveIcon,
  MoreIcon,
  PencilIcon,
  PhoneIcon,
  PlusIcon,
  ReturnIcon,
  WhatsAppIcon,
} from "../components/icons";
import { whatsappLink } from "../lib/phone";

type OpenModal = null | "more" | "override" | "edit" | "note" | "leave" | "return" | { tile: MonthTile };

/**
 * One student, read top to bottom the way the teacher asks about them: who is this, are they up
 * to date (and the button that fixes it if not), how did the year go month by month, and the
 * details. Rare actions (editing, a departure, moving the payment day, the PDF) are one level
 * down, behind "⋯", so the page leads with what is done every week.
 */
export function StudentDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const studentId = Number(id);

  const payments = usePaymentSheet();
  const state = useApi(
    () => Promise.all([getStudent(studentId), getLedger(studentId), listPeriods(studentId)]),
    // `payments.version` refreshes the page after a payment taken from the shared sheet.
    [studentId, payments.version],
  );
  const [openModal, setOpenModal] = useState<OpenModal>(null);
  // The school year the tiles show; null until the teacher (or a link) picks one.
  const [shownYear, setShownYear] = useState<number | null>(null);
  // Offline, the page is read only: the buttons that would save something are switched off.
  const readOnly = useReadOnly();

  // A link to one month (`?month=2026-10`, from the home page's rows) opens that month's tile
  // once the ledger is in, on the right school year. The month then leaves the address, so
  // closing the sheet and refreshing the page doesn't bring it back. A month the page can't show
  // is simply ignored.
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedMonth = searchParams.get("month");
  const loaded = state.status === "success" ? state.data : undefined;
  useEffect(() => {
    if (linkedMonth === null || !loaded) return;
    const [detail, ledger, periods] = loaded;
    const linked = linkedTile(linkedMonth, detail, ledger, isEnrolled(periods));
    if (linked) {
      setShownYear(linked.year);
      setOpenModal({ tile: linked.tile });
    }
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("month");
        return next;
      },
      { replace: true },
    );
  }, [linkedMonth, loaded, setSearchParams]);

  const close = () => setOpenModal(null);
  const handleSaved = () => {
    close();
    state.reload();
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <Link to="/students" className="-ml-1 flex min-h-11 items-center gap-1 font-bold text-brand">
          <ChevronLeftIcon className="h-5 w-5" />
          {t("nav.students")}
        </Link>
        <button
          type="button"
          onClick={() => setOpenModal("more")}
          aria-label={t("student.more")}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-surface text-ink hover:bg-ground"
        >
          <MoreIcon className="h-5 w-5" />
        </button>
      </div>

      <AsyncView state={state} onRetry={state.reload}>
        {([detail, ledger, periods]) => {
          const enrolled = isEnrolled(periods);
          return (
            <>
              <header className="flex items-center gap-4">
                <Avatar name={detail.full_name} size="lg" />
                <div className="min-w-0 flex-1">
                  <h1 className="font-display text-2xl font-extrabold tracking-tight sm:text-3xl">
                    {detail.full_name}
                  </h1>
                  <p className="text-muted">
                    {[
                      detail.school_class ? classLabel(detail.school_class) : t("classes.unassigned"),
                      detail.pack?.name,
                      detail.is_repeating ? t("student.repeatingShort") : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
              </header>

              {detail.phone && <ContactButtons phone={detail.phone} />}

              <StatusCard
                detail={detail}
                ledger={ledger}
                periods={periods}
                enrolled={enrolled}
                onPay={(month) => payments.open(studentId, month)}
                onEdit={() => setOpenModal("edit")}
              />

              <Note note={detail.note} readOnly={readOnly} onEdit={() => setOpenModal("note")} />

              <YearTiles
                detail={detail}
                ledger={ledger}
                enrolled={enrolled}
                shownYear={shownYear}
                onYear={setShownYear}
                onTile={(tile) => setOpenModal({ tile })}
              />

              <Facts detail={detail} />

              {/* Only worth showing once there has been an absence: a single open period since
                  the join date says nothing the facts above don't. */}
              {periods.length > 1 && <Periods periods={periods} />}

              {openModal === "more" && (
                <MoreActions
                  detail={detail}
                  enrolled={enrolled}
                  onClose={close}
                  onPick={(next) => setOpenModal(next)}
                />
              )}
              {typeof openModal === "object" && openModal !== null && (
                <TileDetails
                  tile={openModal.tile}
                  studentId={studentId}
                  monthlyPrice={detail.monthly_price}
                  readOnly={readOnly}
                  payable={!readOnly && payableMonths(ledger.entries, detail.next_expected_date).some(
                    (m) => m.month === openModal.tile.month,
                  )}
                  onClose={close}
                  onPay={() => {
                    close();
                    payments.open(studentId, openModal.tile.month);
                  }}
                  onChanged={(message) => {
                    // `changed` bumps the shared version, which refreshes this page too.
                    close();
                    payments.changed(message);
                  }}
                />
              )}
              {openModal === "override" && (
                <Modal title={t("override.title")} onClose={close}>
                  <CreateOverrideForm studentId={studentId} onSuccess={handleSaved} onCancel={close} />
                </Modal>
              )}
              {(openModal === "leave" || openModal === "return") && (
                <Modal
                  title={t(openModal === "leave" ? "student.leaveTitle" : "student.returnTitle")}
                  onClose={close}
                >
                  <AttendanceForm studentId={studentId} mode={openModal} onSuccess={handleSaved} onCancel={close} />
                </Modal>
              )}
              {openModal === "note" && (
                <NoteSheet
                  studentId={studentId}
                  name={detail.first_name}
                  note={detail.note}
                  onSaved={handleSaved}
                  onClose={close}
                />
              )}
              {openModal === "edit" && (
                <Modal title={t("edit.title")} onClose={close}>
                  <EditStudentForm
                    studentId={studentId}
                    initial={{
                      firstName: detail.first_name,
                      lastName: detail.last_name,
                      isRepeating: detail.is_repeating,
                      phone: detail.phone,
                      classId: detail.class_id,
                      packId: detail.pack_id,
                      customPrice: detail.custom_price,
                      priceNote: detail.price_note,
                      note: detail.note,
                    }}
                    onSuccess={handleSaved}
                    onCancel={close}
                  />
                </Modal>
              )}
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}

/**
 * Where the student stands, as one sentence and the button that acts on it. Owing money comes
 * first, even for someone who has left: that is the case the teacher must not miss.
 */
function StatusCard({
  detail,
  ledger,
  periods,
  enrolled,
  onPay,
  onEdit,
}: {
  detail: StudentDetailOut;
  ledger: LedgerOut;
  periods: EnrollmentPeriod[];
  enrolled: boolean;
  onPay: (month?: string) => void;
  onEdit: () => void;
}) {
  const { t } = useTranslation();
  const readOnly = useReadOnly();
  const months = payableMonths(ledger.entries, detail.next_expected_date);

  if (detail.months_overdue > 0) {
    const oldest = months.find((m) => m.overdue)?.month ?? months[0]!.month;
    const tone = detail.months_overdue === 1 ? "bg-warn-soft text-warn" : "bg-bad-soft text-bad";
    return (
      <Panel className={tone} showing={`owes-${detail.months_overdue}-${detail.amount_owed}`}>
        <p className="font-display text-2xl font-extrabold tracking-tight">
          {t("pay.owes", { count: detail.months_overdue, amount: formatMoney(detail.amount_owed) })}
        </p>
        <p className="text-ink">{t("student.oldestUnpaid", { month: formatMonthInSentence(oldest) })}</p>
        <Button onClick={() => onPay(oldest)} disabled={readOnly} className="min-h-12 text-lg sm:self-start">
          {t("student.payMonth", { month: formatMonthTitle(oldest) })}
        </Button>
      </Panel>
    );
  }
  if (Number(detail.monthly_price) <= 0) {
    return (
      <Panel className="bg-off-soft text-off" showing="no-price">
        <p className="font-display text-2xl font-extrabold tracking-tight">{t("owed.noPrice")}</p>
        <p className="text-ink">{t("student.noPriceText")}</p>
        <Button variant="secondary" onClick={onEdit} disabled={readOnly} className="sm:self-start">
          {t("home.choosePack")}
        </Button>
      </Panel>
    );
  }
  if (!enrolled) {
    const lastLeave = periods
      .map((p) => p.leave_date)
      .filter((d): d is string => d !== null)
      .sort()
      .at(-1);
    return (
      <Panel className="bg-off-soft text-off" showing="left">
        <p className="font-display text-2xl font-extrabold tracking-tight">{t("student.leftTitle")}</p>
        {lastLeave && <p className="text-ink">{t("student.leftText", { date: formatDate(lastLeave) })}</p>}
      </Panel>
    );
  }
  return (
    <Panel className="bg-ok-soft text-ok" showing="paid-up">
      <p className="font-display text-2xl font-extrabold tracking-tight">{t("owed.paidUp")}</p>
      <p className="text-ink">{t("student.nextPayment", { date: formatDate(detail.next_expected_date) })}</p>
      <Button variant="secondary" onClick={() => onPay()} disabled={readOnly} className="sm:self-start">
        {t("home.pay")}
      </Button>
    </Panel>
  );
}

/**
 * Call, or open a WhatsApp chat with the number, side by side. The WhatsApp button opens the app
 * on the teacher's phone (WhatsApp Web on a computer) with the chat ready; she writes and sends
 * the message herself. It's left out when the stored number can't be turned into one WhatsApp
 * accepts (see `whatsappNumber`).
 */
function ContactButtons({ phone }: { phone: string }) {
  const { t } = useTranslation();
  const whatsapp = whatsappLink(phone);
  const button =
    "flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line bg-surface px-5 font-bold text-brand transition active:scale-[0.97] hover:bg-brand-soft";
  return (
    <div className={`grid gap-2 sm:flex ${whatsapp ? "grid-cols-2" : "grid-cols-1"}`}>
      <a href={`tel:${phone.replace(/\s/g, "")}`} aria-label={t("student.callNumber", { phone })} className={button}>
        <PhoneIcon className="h-5 w-5" />
        {t("student.call")}
      </a>
      {whatsapp && (
        <a
          href={whatsapp}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t("student.whatsappNumber", { phone })}
          className={button}
        >
          <WhatsAppIcon className="h-5 w-5" />
          {t("student.whatsapp")}
        </a>
      )}
    </div>
  );
}

function Panel({ className, showing, children }: { className: string; showing: string; children: ReactNode }) {
  const { flashing, done } = useFlashOnChange(showing);
  return (
    <section
      onAnimationEnd={done}
      className={`flex flex-col gap-3 rounded-2xl p-4 sm:p-5 ${className} ${flashing ? "animate-fade-in" : ""}`}
    >
      {children}
    </section>
  );
}

const tileStyles: Record<MonthTile["state"], string> = {
  paid: "border-transparent bg-ok-soft text-ok",
  late: "border-warn bg-ok-soft text-ok",
  due: "border-bad bg-bad-soft text-bad",
  away: "border-dashed border-off bg-off-soft text-off",
  upcoming: "border-line bg-surface text-muted",
  none: "border-transparent bg-transparent text-placeholder",
};

/**
 * The school year as twelve tiles, with arrows to earlier (or prepaid later) years. Opens on the
 * current year; the page holds the year shown, so a link to a month can turn to its year.
 */
function YearTiles({
  detail,
  ledger,
  enrolled,
  shownYear,
  onYear: setYear,
  onTile,
}: {
  detail: StudentDetailOut;
  ledger: LedgerOut;
  enrolled: boolean;
  shownYear: number | null;
  onYear: (year: number) => void;
  onTile: (tile: MonthTile) => void;
}) {
  const { t, i18n } = useTranslation();
  const years = schoolYears(ledger.entries, detail.join_date, ledger.as_of);
  const current = schoolYearStart(ledger.as_of);
  const year =
    shownYear !== null && years.includes(shownYear)
      ? shownYear
      : years.includes(current)
        ? current
        : years[years.length - 1]!;
  const tiles = monthTiles(ledger.entries, year, {
    joinDate: detail.join_date,
    today: ledger.as_of,
    enrolled,
  });
  const index = years.indexOf(year);
  const shortMonth = (month: string) =>
    new Intl.DateTimeFormat(i18n.language, { month: "short" })
      .format(new Date(`${month}-01T00:00:00`))
      .replace(".", "");

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-bold">{t("student.schoolYear", { from: year, to: year + 1 })}</h2>
        {years.length > 1 && (
          <div className="flex gap-2">
            <YearArrow label={t("student.prevYear")} disabled={index === 0} onClick={() => setYear(years[index - 1]!)}>
              <ChevronLeftIcon className="h-5 w-5" />
            </YearArrow>
            <YearArrow
              label={t("student.nextYear")}
              disabled={index === years.length - 1}
              onClick={() => setYear(years[index + 1]!)}
            >
              <ChevronRightIcon className="h-5 w-5" />
            </YearArrow>
          </div>
        )}
      </div>
      <ol className="grid grid-cols-4 gap-2 sm:grid-cols-6">
        {tiles.map((tile) => (
          <Tile key={tile.month} tile={tile} shortMonth={shortMonth(tile.month)} onClick={() => onTile(tile)} />
        ))}
      </ol>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        {(["paid", "late", "due", "away"] as const).map((state) => (
          <li key={state} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={`h-3 w-3 rounded border-2 ${tileStyles[state]}`} />
            {t(`tiles.state.${state}`)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Tile({ tile, shortMonth, onClick }: { tile: MonthTile; shortMonth: string; onClick: () => void }) {
  const { t } = useTranslation();
  const { flashing, done } = useFlashOnChange(tile.state);
  return (
    <li>
      <button
        type="button"
        disabled={tile.state === "none"}
        onClick={onClick}
        onAnimationEnd={done}
        aria-label={`${formatMonthTitle(tile.month)} · ${t(`tiles.state.${tile.state}`)}`}
        className={`flex min-h-16 w-full flex-col items-center justify-center gap-0.5 rounded-xl border-2 px-1 py-2 text-sm font-bold transition-colors active:scale-[0.97] disabled:cursor-default ${tileStyles[tile.state]} ${
          flashing ? "animate-paid-pop" : ""
        }`}
      >
        <span className="capitalize">{shortMonth}</span>
        <span className="text-xs">
          {tile.state === "late"
            ? t("tiles.late", { count: tile.entry?.days_late ?? 0 })
            : tile.state === "none"
              ? "\u00a0"
              : t(`tiles.short.${tile.state}`)}
        </span>
      </button>
    </li>
  );
}

function YearArrow({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-surface text-brand disabled:opacity-40"
    >
      {children}
    </button>
  );
}

/**
 * One month, opened from its tile. A paid month shows what was recorded and, online, lets a typo
 * be fixed (amount or date) or the payment removed; removing asks first, in the same sheet, and
 * says what it does: the month is owed again. Moving a payment to another month is exactly that,
 * followed by recording the right month.
 */
function TileDetails({
  tile,
  studentId,
  monthlyPrice,
  readOnly,
  payable,
  onClose,
  onPay,
  onChanged,
}: {
  tile: MonthTile;
  studentId: number;
  monthlyPrice: string;
  readOnly: boolean;
  payable: boolean;
  onClose: () => void;
  onPay: () => void;
  onChanged: (message: string) => void;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"view" | "edit" | "delete">("view");
  const remove = useMutation(deletePayment);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const e = tile.entry;
  const month = formatMonthTitle(tile.month);
  const paid = e && e.paid_date !== null && e.amount !== null ? { ...e, paid_date: e.paid_date, amount: e.amount } : null;
  // Offline, a correction couldn't be saved: back to the plain details.
  const showing = readOnly ? "view" : mode;

  async function confirmDelete() {
    if (!paid) return;
    setDeleteError(null);
    try {
      await remove.mutate(studentId, paid.cycle_number);
      onChanged(t("payment.deleted", { month }));
    } catch (err) {
      setDeleteError(resolveErrorMessage(err, t));
    }
  }

  return (
    <Modal title={month} onClose={onClose}>
      {paid && showing === "edit" ? (
        <EditPaymentForm
          studentId={studentId}
          entry={paid}
          monthlyPrice={monthlyPrice}
          onCancel={() => setMode("view")}
          onSuccess={() => onChanged(t("payment.corrected", { month }))}
        />
      ) : (
        <div className="flex flex-col gap-4">
          {paid ? (
            <dl className="divide-y divide-line rounded-2xl border border-line">
              <Row label={t("tile.due")}>{formatDate(paid.expected_due_date)}</Row>
              <Row label={t("tile.paidOn")}>{formatDate(paid.paid_date)}</Row>
              <Row label={t("tile.amount")}>{formatMoney(paid.amount)}</Row>
              <Row label={t("tile.lateness")}>
                {(paid.days_late ?? 0) > 0 ? t("tile.days", { count: paid.days_late ?? 0 }) : t("ledger.status.onTime")}
              </Row>
            </dl>
          ) : (
            <p>
              {tile.state === "away"
                ? t("tile.away")
                : tile.state === "due" && e
                  ? t("tile.notPaid", { date: formatDate(e.expected_due_date) })
                  : t("tile.upcoming")}
            </p>
          )}
          {payable && (
            <Button onClick={onPay} className="min-h-12 text-lg">
              {t("student.payMonth", { month })}
            </Button>
          )}
          {paid && !readOnly && showing === "view" && (
            <div className="flex flex-col gap-1">
              <Button variant="secondary" onClick={() => setMode("edit")}>
                {t("tile.editPayment")}
              </Button>
              {/* Red words, no fill: destructive, but a step away from actually deleting. */}
              <button
                type="button"
                onClick={() => setMode("delete")}
                className="min-h-11 rounded-xl px-4 font-bold text-bad transition hover:bg-bad-soft active:scale-[0.97] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                {t("tile.deletePayment")}
              </button>
            </div>
          )}
          {paid && showing === "delete" && (
            <div className="flex flex-col gap-3 rounded-2xl bg-bad-soft p-4">
              <p className="font-bold text-bad">
                {t("tile.deleteConfirm", { month, amount: formatMoney(paid.amount) })}
              </p>
              <p className="text-sm text-ink">{t("tile.deleteMoveHint")}</p>
              {deleteError && <p className="text-sm font-bold text-bad">{deleteError}</p>}
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button variant="ghost" onClick={() => setMode("view")}>
                  {t("common.cancel")}
                </Button>
                <Button variant="danger" pending={remove.status === "pending"} onClick={() => void confirmDelete()}>
                  {t("tile.deleteConfirmButton")}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/**
 * The teacher's own note on the student, private: it never goes on a PDF. Shown under the
 * status so it's read before the money; with none, a quiet link to add one.
 */
function Note({ note, readOnly, onEdit }: { note: string | null; readOnly: boolean; onEdit: () => void }) {
  const { t } = useTranslation();
  if (!note) {
    if (readOnly) return null;
    return (
      <button
        type="button"
        onClick={onEdit}
        className="-my-2 flex min-h-11 items-center gap-1.5 self-start font-bold text-brand"
      >
        <PlusIcon className="h-4 w-4" />
        {t("student.addNote")}
      </button>
    );
  }
  return (
    <section className="flex flex-col gap-1 rounded-2xl border border-line bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-bold text-muted">{t("student.note")}</h2>
        {!readOnly && (
          <button type="button" onClick={onEdit} className="-my-2 min-h-11 px-1 text-sm font-bold text-brand">
            {t("student.editNote")}
          </button>
        )}
      </div>
      <p className="whitespace-pre-line">{note}</p>
    </section>
  );
}

function Facts({ detail }: { detail: StudentDetailOut }) {
  const { t } = useTranslation();
  const average = detail.average_days_late;
  // Two numbers read together in one row, so they don't seem to disagree: how late the student
  // usually pays (their last six payments) and the days late added up since joining (drift).
  const total = detail.cumulative_drift > 0 ? t("punctuality.total", { count: detail.cumulative_drift }) : null;
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">{t("student.details")}</h2>
      <dl className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        <Row label={t("punctuality.label")}>
          {average === null ? (
            // No payment has come due to judge by yet: the total alone.
            (total ?? t("drift.onTrack"))
          ) : (
            <span className="flex flex-col items-end gap-1">
              <PunctualityPill averageDaysLate={average} />
              <span className="text-sm font-normal text-muted">
                {[average === 0 ? t("punctuality.paysOnTime") : t("punctuality.averageShort", { count: average }), total]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
          )}
        </Row>
        <Row label={t("detail.fields.monthlyPrice")}>
          {formatMoney(detail.monthly_price)}
          {/* An agreed price is shown against the pack's, so the exception is visible. */}
          {detail.custom_price !== null && detail.pack && (
            <span className="block text-sm font-normal text-muted">
              {t("student.insteadOf", { price: formatMoney(detail.pack.price) })}
              {detail.price_note ? ` · ${detail.price_note}` : ""}
            </span>
          )}
        </Row>
        <Row label={t("student.pack")}>
          {detail.pack ? packWithLevel(detail.pack.name, detail.pack.level) : t("student.noPack")}
          {detail.pack && detail.school_class && detail.school_class.level !== detail.pack.level && (
            <span className="block text-sm font-normal text-warn">
              {t("student.levelMismatch", { packLevel: detail.pack.level, classLevel: detail.school_class.level })}
            </span>
          )}
        </Row>
        <Row label={t("detail.fields.class")}>
          {detail.school_class ? (
            <Link
              to={`/settings/classes/${detail.school_class.id}`}
              className="inline-flex min-h-11 items-center text-brand underline"
            >
              {classLabel(detail.school_class)}
            </Link>
          ) : (
            t("classes.unassigned")
          )}
        </Row>
        <Row label={t("detail.fields.phone")}>{detail.phone ?? "—"}</Row>
        <Row label={t("detail.fields.joinDate")}>{formatDate(detail.join_date)}</Row>
        <Row label={t("detail.fields.totalPaid")}>
          {formatMoney(detail.total_paid)}
          <span className="block text-sm font-normal text-muted">
            {t("student.paymentsCount", { count: detail.payments_count })}
          </span>
        </Row>
      </dl>
    </section>
  );
}

/** "Pack TC Sciences · TC", but just the name when it already says the level. */
function packWithLevel(name: string, level: string): string {
  return name.includes(level) ? name : `${name} · ${level}`;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-bold">{children}</dd>
    </div>
  );
}

function Periods({ periods }: { periods: EnrollmentPeriod[] }) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">{t("student.attendance")}</h2>
      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {periods.map((p) => (
          <li key={p.id} className="flex flex-col gap-0.5 px-4 py-3">
            <span className="font-bold">
              {formatDate(p.entry_date)} → {p.leave_date ? formatDate(p.leave_date) : t("student.stillHere")}
            </span>
            {p.leave_reason && <span className="text-sm text-muted">{p.leave_reason}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Things done a few times a year, kept off the page itself. */
function MoreActions({
  detail,
  enrolled,
  onClose,
  onPick,
}: {
  detail: StudentDetailOut;
  enrolled: boolean;
  onClose: () => void;
  onPick: (modal: "edit" | "leave" | "return" | "override") => void;
}) {
  const { t } = useTranslation();
  const readOnly = useReadOnly();
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloadError(null);
    try {
      const slug = slugify(detail.full_name);
      const stem = t("detail.pdfFilename", { id: detail.id, name: slug ? `-${slug}` : "" });
      await downloadFile(`/students/${detail.id}/ledger.pdf`, `${stem}.pdf`);
    } catch (err) {
      setDownloadError(resolveErrorMessage(err, t));
    }
  }

  // Each action leads with its own picture, so the teacher can find one without reading the list.
  const items: { label: string; icon: ComponentType<SVGProps<SVGSVGElement>>; onClick: () => void }[] = [
    { label: t("detail.actions.edit"), icon: PencilIcon, onClick: () => onPick("edit") },
    // Follows the enrolment, not `status`: see `isEnrolled`.
    {
      label: t(enrolled ? "student.markLeft" : "student.markReturned"),
      icon: enrolled ? LeaveIcon : ReturnIcon,
      onClick: () => onPick(enrolled ? "leave" : "return"),
    },
    { label: t("detail.actions.addOverride"), icon: CalendarIcon, onClick: () => onPick("override") },
    { label: t("detail.downloadPdf"), icon: DownloadIcon, onClick: () => void handleDownload() },
  ];
  return (
    <Modal title={detail.full_name} onClose={onClose}>
      <ul className="-mx-2 flex flex-col">
        {items.map(({ label, icon: Icon, onClick }) => (
          <li key={label}>
            <button
              type="button"
              onClick={onClick}
              disabled={readOnly}
              className="flex min-h-14 w-full items-center gap-3 rounded-xl px-3 text-left font-bold hover:bg-ground disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
                <Icon className="h-5 w-5" />
              </span>
              <span className="min-w-0 flex-1">{label}</span>
              <ChevronRightIcon className="h-5 w-5 shrink-0 text-muted" />
            </button>
          </li>
        ))}
      </ul>
      {downloadError && <p className="mt-2 text-sm font-bold text-bad">{downloadError}</p>}
    </Modal>
  );
}

/**
 * The tile a `?month=YYYY-MM` link points at, with its school year, or null when the page has no
 * such tile to open: not a month, a year outside the student's, or a month nothing was expected
 * in (before joining, after leaving), whose tile can't be tapped either.
 */
function linkedTile(
  month: string,
  detail: StudentDetailOut,
  ledger: LedgerOut,
  enrolled: boolean,
): { tile: MonthTile; year: number } | null {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return null;
  const year = schoolYearStart(`${month}-01`);
  if (!schoolYears(ledger.entries, detail.join_date, ledger.as_of).includes(year)) return null;
  const tile = monthTiles(ledger.entries, year, { joinDate: detail.join_date, today: ledger.as_of, enrolled }).find(
    (t) => t.month === month,
  );
  return tile && tile.state !== "none" ? { tile, year } : null;
}

/**
 * Whether the student is currently enrolled, read from their periods rather than `status`. A
 * student set to "Inactif" by hand still has an open period, so offering "Réinscrire" there would
 * be refused by the server; "Marquer comme parti" is the action that actually records the
 * departure (and is where the dashboard's "sans date de départ" warning sends the teacher).
 */
function isEnrolled(periods: { leave_date: string | null }[]): boolean {
  return periods.some((p) => p.leave_date === null);
}
