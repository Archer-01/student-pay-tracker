import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getLedger, getStudent, listPeriods } from "../api/endpoints";
import { downloadFile } from "../api/client";
import type { EnrollmentPeriod, LedgerOut, StudentDetailOut } from "../api/types";
import { useApi } from "../lib/useApi";
import { formatMoney } from "../lib/money";
import { formatDate, formatMonthTitle } from "../lib/dates";
import { classLabel } from "../lib/classes";
import { slugify } from "../lib/slug";
import { resolveErrorMessage } from "../lib/errors";
import { payableMonths } from "../lib/paymentDefaults";
import { monthTiles, schoolYearStart, schoolYears, type MonthTile } from "../lib/schoolYear";
import { usePaymentSheet } from "../lib/paymentSheetContext";
import { useFlashOnChange } from "../lib/useFlashOnChange";
import { CreateOverrideForm } from "../components/students/CreateOverrideForm";
import { EditStudentForm } from "../components/students/EditStudentForm";
import { AttendanceForm } from "../components/students/AttendanceForm";
import { AsyncView, Button, Modal } from "../components/ui";
import { Avatar } from "../components/people";
import { ChevronLeftIcon, ChevronRightIcon, MoreIcon, PhoneIcon, WhatsAppIcon } from "../components/icons";
import { whatsappLink } from "../lib/phone";

type OpenModal = null | "more" | "override" | "edit" | "leave" | "return" | { tile: MonthTile };

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

              <YearTiles
                detail={detail}
                ledger={ledger}
                enrolled={enrolled}
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
                  payable={payableMonths(ledger.entries, detail.next_expected_date).some(
                    (m) => m.month === openModal.tile.month,
                  )}
                  onClose={close}
                  onPay={() => {
                    close();
                    payments.open(studentId, openModal.tile.month);
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
  const months = payableMonths(ledger.entries, detail.next_expected_date);

  if (detail.months_overdue > 0) {
    const oldest = months.find((m) => m.overdue)?.month ?? months[0]!.month;
    const tone = detail.months_overdue === 1 ? "bg-warn-soft text-warn" : "bg-bad-soft text-bad";
    return (
      <Panel className={tone} showing={`owes-${detail.months_overdue}-${detail.amount_owed}`}>
        <p className="font-display text-2xl font-extrabold tracking-tight">
          {t("pay.owes", { count: detail.months_overdue, amount: formatMoney(detail.amount_owed) })}
        </p>
        <p className="text-ink">{t("student.oldestUnpaid", { month: formatMonthTitle(oldest) })}</p>
        <Button onClick={() => onPay(oldest)} className="min-h-12 text-lg sm:self-start">
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
        <Button variant="secondary" onClick={onEdit} className="sm:self-start">
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
      <Button variant="secondary" onClick={() => onPay()} className="sm:self-start">
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

/** The school year as twelve tiles, with arrows to earlier (or prepaid later) years. */
function YearTiles({
  detail,
  ledger,
  enrolled,
  onTile,
}: {
  detail: StudentDetailOut;
  ledger: LedgerOut;
  enrolled: boolean;
  onTile: (tile: MonthTile) => void;
}) {
  const { t, i18n } = useTranslation();
  const years = schoolYears(ledger.entries, detail.join_date, ledger.as_of);
  const [year, setYear] = useState(() => {
    const current = schoolYearStart(ledger.as_of);
    return years.includes(current) ? current : years[years.length - 1]!;
  });
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

function TileDetails({
  tile,
  payable,
  onClose,
  onPay,
}: {
  tile: MonthTile;
  payable: boolean;
  onClose: () => void;
  onPay: () => void;
}) {
  const { t } = useTranslation();
  const e = tile.entry;
  return (
    <Modal title={formatMonthTitle(tile.month)} onClose={onClose}>
      <div className="flex flex-col gap-4">
        {e?.paid_date ? (
          <dl className="divide-y divide-line rounded-2xl border border-line">
            <Row label={t("tile.due")}>{formatDate(e.expected_due_date)}</Row>
            <Row label={t("tile.paidOn")}>{formatDate(e.paid_date)}</Row>
            <Row label={t("tile.amount")}>{e.amount ? formatMoney(e.amount) : "—"}</Row>
            <Row label={t("tile.lateness")}>
              {(e.days_late ?? 0) > 0 ? t("drift.late", { count: e.days_late ?? 0 }) : t("ledger.status.onTime")}
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
            {t("student.payMonth", { month: formatMonthTitle(tile.month) })}
          </Button>
        )}
      </div>
    </Modal>
  );
}

function Facts({ detail }: { detail: StudentDetailOut }) {
  const { t } = useTranslation();
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">{t("student.details")}</h2>
      <dl className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        <Row label={t("student.totalLate")}>
          {detail.cumulative_drift > 0 ? t("student.days", { count: detail.cumulative_drift }) : t("drift.onTrack")}
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
          {detail.pack ? `${detail.pack.name} · ${detail.pack.level}` : t("student.noPack")}
          {detail.pack && detail.school_class && detail.school_class.level !== detail.pack.level && (
            <span className="block text-sm font-normal text-warn">
              {t("student.levelMismatch", { packLevel: detail.pack.level, classLevel: detail.school_class.level })}
            </span>
          )}
        </Row>
        <Row label={t("detail.fields.class")}>
          {detail.school_class ? (
            <Link to={`/settings/classes/${detail.school_class.id}`} className="text-brand underline">
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

  const items: { label: string; onClick: () => void }[] = [
    { label: t("detail.actions.edit"), onClick: () => onPick("edit") },
    // Follows the enrolment, not `status`: see `isEnrolled`.
    {
      label: t(enrolled ? "student.markLeft" : "student.markReturned"),
      onClick: () => onPick(enrolled ? "leave" : "return"),
    },
    { label: t("detail.actions.addOverride"), onClick: () => onPick("override") },
    { label: t("detail.downloadPdf"), onClick: () => void handleDownload() },
  ];
  return (
    <Modal title={detail.full_name} onClose={onClose}>
      <ul className="-mx-2 flex flex-col">
        {items.map((item) => (
          <li key={item.label}>
            <button
              type="button"
              onClick={item.onClick}
              className="flex min-h-14 w-full items-center justify-between gap-3 rounded-xl px-3 text-left font-bold hover:bg-ground"
            >
              {item.label}
              <ChevronRightIcon className="h-5 w-5 text-muted" />
            </button>
          </li>
        ))}
      </ul>
      {downloadError && <p className="mt-2 text-sm font-bold text-bad">{downloadError}</p>}
    </Modal>
  );
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
