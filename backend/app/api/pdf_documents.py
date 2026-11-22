"""What each of the four PDFs says: a student's history, the month, the year, a class.

Built from the blocks in :mod:`app.api.pdf_export`, and laid out like the app's own screens so
paper and screen read the same: the student PDF opens on the student page's status card and
month tiles, the reports on Bilan's figures and share bar. The helpers that decide a word or a
colour are pure functions, tested on their own in ``tests/unit/test_pdf_documents.py``.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import Response
from reportlab.platypus import Flowable

from app.api.pdf_export import (
    SCHOOL_INK,
    Bar,
    BarChart,
    Column,
    Fact,
    Figure,
    Pill,
    Tile,
    Tone,
    cell,
    facts,
    figures,
    gap,
    heading,
    legend_amount,
    money,
    note,
    render_pdf,
    section_title,
    share_bar,
    status_card,
    table,
    year_tiles,
)
from app.core.i18n import (
    format_day,
    format_percent,
    month_name,
    month_short,
    translate,
)
from app.models import Student, StudentStatus
from app.services.class_service import RosterRow
from app.services.ledger_service import LedgerEntry, StudentSummary
from app.services.pricing_service import PriceStatus
from app.services.reports_service import AnnualReport, MonthlyReport
from app.services.school_share import ShareSplit
from app.services.school_year import MonthTile, month_tiles, school_years

# --------------------------------------------------------------------------- #
# Every page
# --------------------------------------------------------------------------- #


def footer_text(locale: str, made_on: date, as_of: date | None = None) -> str:
    """When the PDF was made, and the date its figures are for when that is another day."""
    text = translate("pdf.made_on", locale, date=format_day(made_on, locale))
    if as_of is not None and as_of != made_on:
        text += " · " + translate("pdf.figures_as_of", locale, date=format_day(as_of, locale))
    return text


def respond(
    story: Sequence[Flowable],
    *,
    title: str,
    teacher: str,
    locale: str,
    filename: str,
    made_on: date,
    as_of: date | None = None,
) -> Response:
    return render_pdf(
        story,
        title=title,
        teacher=translate("pdf.teacher", locale, name=teacher),
        footer=footer_text(locale, made_on, as_of),
        page_label=lambda page, total: translate("pdf.page", locale, page=page, total=total),
        filename=filename,
    )


def month_title(day: date, locale: str) -> str:
    """ "Novembre 2026"."""
    return f"{month_name(day.month, locale)} {day.year}"


def class_label(student: Student, locale: str) -> str | None:
    if student.school_class is None:
        return None
    return f"{student.school_class.level.value} — {student.school_class.name}"


def pack_label(student: Student, locale: str) -> str:
    """The pack name, plus its level only when that differs from the student's class.

    Printing the level unconditionally reads as a stutter — "2BAC — Groupe A · Maths seul · 2BAC" —
    since the class already says it. When they disagree, though, that is exactly what a reader
    needs to see.
    """
    if student.pack is None:
        return translate("pdf.no_pack", locale)
    same_level = (
        student.school_class is not None and student.school_class.level is student.pack.level
    )
    return student.pack.name if same_level else f"{student.pack.name} · {student.pack.level.value}"


def _share_block(share: ShareSplit, total: Decimal, locale: str) -> list[Flowable]:
    """The share bar, or nothing when there is no share to show (0%, or nothing came in)."""
    if share.percent <= 0 or total <= 0:
        return []
    yours = legend_amount(translate("pdf.share.yours", locale), money(share.teacher, locale))
    school_label = translate(
        "pdf.share.school", locale, percent=format_percent(share.percent, locale)
    )
    schools = legend_amount(school_label, money(share.school, locale))
    return [gap(12), *share_bar(share.teacher, total, yours, schools)]


# --------------------------------------------------------------------------- #
# A student's history
# --------------------------------------------------------------------------- #


def ledger_status(
    summary: StudentSummary,
    entries: Sequence[LedgerEntry],
    price_status: PriceStatus,
    *,
    enrolled: bool,
    left_on: date | None,
    as_of: date,
    locale: str,
) -> tuple[str, str | None, Tone]:
    """The status card, decided as the student page decides it: what's owed first, then free or
    no price, then gone, else up to date."""
    if summary.months_overdue > 0:
        owed = [
            e
            for e in entries
            if e.paid_date is None
            and not e.suspended
            and not e.waived
            and e.expected_due_date <= as_of
        ]
        title = translate(
            "pdf.ledger.owes",
            locale,
            count=summary.months_overdue,
            amount=money(summary.amount_owed, locale),
        )
        text = (
            translate(
                "pdf.ledger.oldest_unpaid",
                locale,
                month=month_title(owed[0].expected_due_date, locale),
            )
            if owed
            else None
        )
        return title, text, "warn" if summary.months_overdue == 1 else "bad"
    if price_status == "free":
        # Free on purpose (decision 0011), not a price nobody set: this goes to parents.
        return translate("pdf.free", locale), translate("pdf.ledger.free_text", locale), "off"
    if price_status == "unset":
        return (
            translate("pdf.no_price", locale),
            translate("pdf.ledger.no_price_text", locale),
            "off",
        )
    if not enrolled:
        text = (
            translate("pdf.ledger.left_text", locale, date=format_day(left_on, locale))
            if left_on
            else None
        )
        return translate("pdf.ledger.left", locale), text, "off"
    return (
        translate("pdf.paid_up", locale),
        translate(
            "pdf.ledger.next_payment",
            locale,
            date=format_day(summary.next_expected_date, locale),
        ),
        "ok",
    )


def tile_word(tile: MonthTile, locale: str) -> str:
    """The small word under a month tile, as on the student page."""
    if tile.state == "late" and tile.entry is not None:
        return translate("pdf.tile.late", locale, count=tile.entry.days_late or 0)
    if tile.state == "none":
        return ""
    return translate(f"pdf.tile.{tile.state}", locale)


def timing_pill(entry: LedgerEntry, locale: str) -> Pill:
    """On time in green, or how late in amber."""
    late = entry.days_late or 0
    if late > 0:
        return Pill(translate("pdf.days_late", locale, count=late), "warn")
    return Pill(translate("pdf.on_time", locale), "ok")


def ledger_story(
    student: Student,
    summary: StudentSummary,
    entries: Sequence[LedgerEntry],
    price: Decimal,
    *,
    enrolled: bool,
    left_on: date | None,
    as_of: date,
    locale: str,
    price_status: PriceStatus,
) -> list[Flowable]:
    sub = " · ".join(
        part
        for part in (class_label(student, locale), pack_label(student, locale), student.phone)
        if part
    )
    title, text, tone = ledger_status(
        summary,
        entries,
        price_status,
        enrolled=enrolled,
        left_on=left_on,
        as_of=as_of,
        locale=locale,
    )
    agreed = (
        translate("pdf.ledger.agreed_price", locale, note=student.price_note)
        if student.custom_price is not None and student.price_note
        else None
    )
    story: list[Flowable] = [
        *heading(translate("pdf.ledger.title", locale), student.full_name, sub),
        gap(14),
        status_card(title, text, tone),
        gap(14),
        facts(
            [
                Fact(translate("pdf.ledger.monthly_price", locale), money(price, locale), agreed),
                Fact(translate("pdf.ledger.joined", locale), format_day(student.join_date, locale)),
                Fact(
                    translate("pdf.ledger.total_paid", locale),
                    money(summary.total_paid, locale),
                ),
                Fact(
                    translate("pdf.ledger.lateness", locale),
                    translate("pdf.days", locale, count=summary.cumulative_drift),
                ),
            ]
        ),
    ]
    # Newest school year first: it's the one the reader is asking about.
    for start in reversed(school_years(entries, student.join_date, as_of)):
        tiles = month_tiles(
            entries,
            start,
            join_date=student.join_date,
            today=as_of,
            enrolled=enrolled,
            free=price_status == "free",
        )
        label = translate("pdf.ledger.school_year", locale, start=start, end=start + 1)
        story += [
            gap(12),
            *year_tiles(
                label,
                [
                    Tile(month_short(t.month.month, locale), tile_word(t, locale), t.state)
                    for t in tiles
                ],
            ),
        ]

    story += [gap(18), section_title(translate("pdf.ledger.payments", locale)), gap(4)]
    paid = sorted(
        (e for e in entries if e.paid_date is not None),
        key=lambda e: e.expected_due_date,
        reverse=True,
    )
    if not paid:
        story.append(note(translate("pdf.ledger.empty", locale)))
        return story
    columns = [
        Column(translate("pdf.ledger.col.month", locale), 0.3),
        Column(translate("pdf.ledger.col.paid_on", locale), 0.25),
        Column(translate("pdf.ledger.col.amount", locale), 0.2, "RIGHT"),
        Column(translate("pdf.ledger.col.timing", locale), 0.25, "RIGHT"),
    ]
    rows = [
        [
            cell(month_title(e.expected_due_date, locale)),
            cell(format_day(e.paid_date, locale)) if e.paid_date else "",
            cell(money(e.amount or Decimal(0), locale), numeric=True, align="RIGHT"),
            timing_pill(e, locale),
        ]
        for e in paid
    ]
    story.append(table(columns, rows))
    return story


# --------------------------------------------------------------------------- #
# The month
# --------------------------------------------------------------------------- #


def monthly_story(
    report: MonthlyReport, labels: dict[int, str | None], locale: str
) -> list[Flowable]:
    """``labels`` gives each student's class, by id, for the grey line under their name."""
    when = date(report.year, report.month, 1)
    in_month = month_name(report.month, locale, in_sentence=True)
    owing = [row for row in report.rows if row.outstanding > 0]
    paid = [row for row in report.rows if row.collected > 0]
    share = report.share
    collected_hint = (
        translate("pdf.share.yours_of", locale, amount=money(share.teacher, locale))
        if share.percent > 0 and report.total_collected > 0
        else None
    )
    story: list[Flowable] = [
        *heading(translate("pdf.monthly.eyebrow", locale), month_title(when, locale)),
        gap(16),
        figures(
            [
                Figure(
                    translate("pdf.monthly.collected", locale, month=in_month),
                    money(report.total_collected, locale),
                    collected_hint,
                ),
                Figure(
                    translate(
                        "pdf.monthly.outstanding", locale, date=format_day(report.as_of, locale)
                    ),
                    money(report.total_outstanding, locale),
                    translate("pdf.students", locale, count=len(owing)) if owing else None,
                    "bad" if report.total_outstanding > 0 else None,
                ),
                Figure(
                    translate("pdf.monthly.students", locale),
                    str(len(report.rows)),
                    translate("pdf.monthly.paid_count", locale, count=len(paid)),
                ),
            ]
        ),
        *_share_block(share, report.total_collected, locale),
        gap(20),
        section_title(translate("pdf.monthly.by_student", locale)),
        gap(4),
    ]
    if not report.rows:
        story.append(note(translate("pdf.monthly.empty", locale)))
        return story

    columns = [
        Column(translate("pdf.col.student", locale), 0.4),
        Column(translate("pdf.col.price", locale), 0.17, "RIGHT"),
        Column(translate("pdf.monthly.col.paid_in", locale, month=in_month), 0.22, "RIGHT"),
        Column(translate("pdf.col.still_owed", locale), 0.21, "RIGHT"),
    ]
    rows: list[list[Any]] = []
    for row in report.rows:
        former = translate("pdf.former", locale) if row.status is StudentStatus.INACTIVE else None
        sub = " · ".join(p for p in (labels.get(row.student_id), former) if p) or None
        rows.append(
            [
                cell(row.name, sub=sub, bold=True),
                cell(money(row.fee, locale), numeric=True, muted=True, align="RIGHT"),
                cell(money(row.collected, locale), numeric=True, align="RIGHT")
                if row.collected > 0
                else cell("—", muted=True, align="RIGHT"),
                owed_pill(row.outstanding, row.price_status, locale),
            ]
        )
    total = [
        cell(translate("pdf.total", locale), bold=True),
        "",
        cell(money(report.total_collected, locale), numeric=True, bold=True, align="RIGHT"),
        cell(money(report.total_outstanding, locale), numeric=True, bold=True, align="RIGHT"),
    ]
    story.append(table(columns, rows, total=total))
    return story


def owed_pill(outstanding: Decimal, price_status: PriceStatus, locale: str) -> Pill:
    """What's still owed in red, else "À jour", or "Gratuit" / "Sans tarif" for someone not
    billed."""
    if outstanding > 0:
        return Pill(money(outstanding, locale), "bad")
    if price_status != "priced":
        return _unbilled_pill(price_status, locale)
    return Pill(translate("pdf.paid_up", locale), "ok")


# --------------------------------------------------------------------------- #
# The year
# --------------------------------------------------------------------------- #


def _unbilled_pill(price_status: PriceStatus, locale: str) -> Pill:
    """« Gratuit » for a student free on purpose (decision 0011), « Sans tarif » for one with no
    price yet: grey either way, never a debt."""
    return Pill(translate("pdf.free" if price_status == "free" else "pdf.no_price", locale), "off")


def is_future(year: int, month: int, today: date) -> bool:
    """A month that hasn't started yet: nothing in it can be read as "nothing came in"."""
    return (year, month) > (today.year, today.month)


def annual_story(report: AnnualReport, today: date, locale: str) -> list[Flowable]:
    earning = [m for m in report.months if m.collected > 0]
    best = max(earning, key=lambda m: m.collected) if earning else None
    # Averaged over the months that actually earned, not over twelve — a year that only ran from
    # September would otherwise look like it took a third of what it did.
    average = report.total_collected / len(earning) if earning else Decimal("0")
    story: list[Flowable] = [
        *heading(translate("pdf.annual.eyebrow", locale), str(report.year)),
        gap(16),
        figures(
            [
                Figure(
                    translate("pdf.annual.total", locale), money(report.total_collected, locale)
                ),
                Figure(translate("pdf.annual.payments", locale), str(report.payments_count)),
                Figure(
                    translate("pdf.annual.average", locale),
                    money(average.quantize(Decimal("0.01")), locale),
                    translate("pdf.annual.average_hint", locale),
                ),
                Figure(
                    translate("pdf.annual.best", locale),
                    month_name(best.month, locale) if best else "—",
                ),
            ]
        ),
        *_share_block(report.share, report.total_collected, locale),
    ]
    if not report.payments_count:
        story += [gap(20), note(translate("pdf.annual.empty", locale))]
        return story

    story += [
        gap(22),
        BarChart(
            [
                Bar(
                    month_short(m.month, locale),
                    m.collected,
                    money(m.collected, locale, currency=False),
                    highlight=best is not None and m.month == best.month,
                    future=is_future(report.year, m.month, today),
                )
                for m in report.months
            ]
        ),
        gap(18),
    ]
    show_share = report.share.percent > 0
    columns = [
        Column(translate("pdf.annual.col.month", locale), 0.24),
        Column(translate("pdf.annual.payments", locale), 0.16, "RIGHT"),
        Column(translate("pdf.annual.col.collected", locale), 0.2, "RIGHT"),
    ]
    if show_share:
        columns += [
            Column(translate("pdf.share.yours", locale), 0.2, "RIGHT"),
            Column(translate("pdf.share.school_short", locale), 0.2, "RIGHT"),
        ]
    else:
        columns[0] = Column(columns[0].title, 0.64)
    rows: list[list[Any]] = []
    for m in report.months:
        name = month_name(m.month, locale)
        if is_future(report.year, m.month, today):
            rows.append(
                [
                    cell(name, muted=True),
                    cell(translate("pdf.annual.to_come", locale), muted=True, align="RIGHT"),
                ]
                + [""] * (len(columns) - 2)
            )
            continue
        if m.collected <= 0:
            rows.append(
                [cell(name, muted=True), cell("0", numeric=True, muted=True, align="RIGHT")]
                + [cell("—", muted=True, align="RIGHT")] * (len(columns) - 2)
            )
            continue
        row = [
            cell(name),
            cell(str(m.payments_count), numeric=True, align="RIGHT"),
            cell(money(m.collected, locale), numeric=True, bold=True, align="RIGHT"),
        ]
        if show_share:
            row += [
                cell(money(m.share.teacher, locale), numeric=True, align="RIGHT"),
                cell(money(m.share.school, locale), numeric=True, color=SCHOOL_INK, align="RIGHT"),
            ]
        rows.append(row)
    total = [
        cell(translate("pdf.total", locale), bold=True),
        cell(str(report.payments_count), numeric=True, bold=True, align="RIGHT"),
        cell(money(report.total_collected, locale), numeric=True, bold=True, align="RIGHT"),
    ]
    if show_share:
        total += [
            cell(money(report.share.teacher, locale), numeric=True, bold=True, align="RIGHT"),
            cell(
                money(report.share.school, locale),
                numeric=True,
                bold=True,
                color=SCHOOL_INK,
                align="RIGHT",
            ),
        ]
    story.append(table(columns, rows, total=total))
    return story


# --------------------------------------------------------------------------- #
# A class
# --------------------------------------------------------------------------- #


def roster_pill(row: RosterRow, locale: str) -> Pill:
    """Where a student of the class stands, in the app's words and colours."""
    if row.student.status is StudentStatus.INACTIVE:
        return Pill(translate("pdf.former", locale), "off")
    if row.months_overdue > 0:
        tone: Tone = "warn" if row.months_overdue == 1 else "bad"
        return Pill(translate("pdf.months_unpaid", locale, count=row.months_overdue), tone)
    if row.price_status != "priced":
        return _unbilled_pill(row.price_status, locale)
    return Pill(translate("pdf.paid_up", locale), "ok")


def roster_story(title: str, rows: Sequence[RosterRow], locale: str) -> list[Flowable]:
    owed = sum((row.amount_owed for row in rows), Decimal("0"))
    owing = [row for row in rows if row.amount_owed > 0]
    up_to_date = [
        row
        for row in rows
        if row.months_overdue == 0
        and row.price_status == "priced"
        and row.student.status is not StudentStatus.INACTIVE
    ]
    story: list[Flowable] = [
        *heading(translate("pdf.roster.title", locale), title),
        gap(16),
        figures(
            [
                Figure(translate("pdf.monthly.students", locale), str(len(rows))),
                Figure(translate("pdf.roster.up_to_date", locale), str(len(up_to_date))),
                Figure(
                    translate("pdf.roster.outstanding", locale),
                    money(owed, locale),
                    translate("pdf.students", locale, count=len(owing)) if owing else None,
                    "bad" if owed > 0 else None,
                ),
            ]
        ),
        gap(20),
    ]
    if not rows:
        story.append(note(translate("pdf.roster.empty", locale)))
        return story
    columns = [
        Column(translate("pdf.col.student", locale), 0.36),
        Column(translate("pdf.col.price", locale), 0.16, "RIGHT"),
        Column(translate("pdf.roster.col.situation", locale), 0.27, "RIGHT"),
        Column(translate("pdf.col.still_owed", locale), 0.21, "RIGHT"),
    ]
    body = [
        [
            cell(row.student.full_name, sub=row.student.phone, bold=True),
            cell(money(row.monthly_price, locale), numeric=True, muted=True, align="RIGHT"),
            roster_pill(row, locale),
            cell(money(row.amount_owed, locale), numeric=True, align="RIGHT")
            if row.amount_owed > 0
            else cell("—", muted=True, align="RIGHT"),
        ]
        for row in rows
    ]
    total = [
        cell(translate("pdf.total", locale), bold=True),
        "",
        "",
        cell(money(owed, locale), numeric=True, bold=True, align="RIGHT"),
    ]
    story.append(table(columns, body, total=total))
    return story
