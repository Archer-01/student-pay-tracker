"""PDF rendering for the exports (reportlab).

One document shell serves all three exports so they read as the same product: a title block, an
optional strip of headline figures, an optional two-column detail block, the table, and a footer
saying when it was produced and as of when.

Uses reportlab's built-in Helvetica, which covers Latin-1 (including French accents). Arabic-script
names are not shaped/rendered — a known limitation.
"""

import io
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape

from fastapi import Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.paragraph import Paragraph

_INK = colors.HexColor("#0f172a")  # slate-900
_MUTED = colors.HexColor("#64748b")  # slate-500
_HEADER_BG = colors.HexColor("#334155")  # slate-700
_GRID = colors.HexColor("#cbd5e1")  # slate-300
_PANEL = colors.HexColor("#f1f5f9")  # slate-100
_RULE = colors.HexColor("#94a3b8")  # slate-400
_ZEBRA = colors.HexColor("#f8fafc")  # slate-50
_CONTENT_WIDTH = landscape(A4)[0] - 30 * mm


@dataclass(frozen=True)
class Stat:
    """One headline figure in the summary strip: a small label over a large value."""

    label: str
    value: str


def slugify_name(name: str) -> str:
    """An ASCII, filename-safe slug of a name (accents folded, non-alphanumerics hyphenated).

    Returns "" for names that carry no ASCII letters/digits (e.g. Arabic script) — the caller
    then falls back to an id-only filename rather than emitting an empty or non-ASCII one.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", folded).strip("-").lower()


def _title_block(title: str, subtitle: str | None, meta: str | None) -> list[Flowable]:
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "DocTitle", parent=styles["Title"], fontSize=20, leading=24, alignment=0,
        textColor=_INK, spaceAfter=2,
    )
    sub = ParagraphStyle(
        "DocSubtitle", parent=styles["Normal"], fontSize=12, leading=15,
        textColor=_INK, spaceAfter=1,
    )
    small = ParagraphStyle(
        "DocMeta", parent=styles["Normal"], fontSize=9, leading=12, textColor=_MUTED
    )
    block: list[Flowable] = [Paragraph(escape(title), heading)]
    if subtitle:
        block.append(Paragraph(f"<b>{escape(subtitle)}</b>", sub))
    if meta:
        block.append(Paragraph(escape(meta), small))
    return block


def _stats_strip(stats: Sequence[Stat]) -> Flowable:
    """Headline figures across the page — what the teacher reads before the table."""
    labels = [Paragraph(f"<font size=7 color='#64748b'>{escape(s.label.upper())}</font>", _cell())
              for s in stats]
    values = [Paragraph(f"<font size=13 color='#0f172a'><b>{escape(s.value)}</b></font>", _cell())
              for s in stats]
    width = _CONTENT_WIDTH / max(len(stats), 1)
    table = Table([labels, values], colWidths=[width] * len(stats))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _PANEL),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("TOPPADDING", (0, 1), (-1, 1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Hairlines between figures, none around the outside.
                ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white),
            ]
        )
    )
    return table


def _cell() -> ParagraphStyle:
    return ParagraphStyle("Cell", fontName="Helvetica", fontSize=9, leading=11)


def _facts_block(facts: Sequence[tuple[str, str]]) -> Flowable:
    """Secondary detail as label/value pairs, laid out in three columns."""
    columns = 3
    rows: list[list[Flowable | str]] = []
    for start in range(0, len(facts), columns):
        chunk = list(facts[start : start + columns])
        cells: list[Flowable | str] = []
        for label, value in chunk:
            cells.append(
                Paragraph(
                    f"<font size=7 color='#64748b'>{escape(label.upper())}</font><br/>"
                    f"<font size=9 color='#0f172a'>{escape(value)}</font>",
                    _cell(),
                )
            )
        cells += [""] * (columns - len(chunk))
        rows.append(cells)

    table = Table(rows, colWidths=[_CONTENT_WIDTH / columns] * columns)
    table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _column_widths(data: Sequence[Sequence[str]]) -> list[float]:
    """Spread the table across the page, proportional to each column's widest cell.

    Left to itself reportlab sizes to content and centres the result, which leaves a narrow table
    floating in the middle of a landscape page. Weighting by content keeps "Cycle" narrow and the
    date columns wide while still filling the width.
    """
    widths = [max(len(str(row[i])) for row in data) + 2 for i in range(len(data[0]))]
    total = sum(widths)
    return [_CONTENT_WIDTH * w / total for w in widths]


def _data_table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> Flowable:
    data = [list(header)] + [list(row) for row in rows]
    table = Table(data, repeatRows=1, colWidths=_column_widths(data), hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ZEBRA]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def render_report_pdf(
    *,
    title: str,
    header: Sequence[str],
    rows: Iterable[Sequence[str]],
    filename: str,
    subtitle: str | None = None,
    meta: str | None = None,
    stats: Sequence[Stat] = (),
    facts: Sequence[tuple[str, str]] = (),
    footer: str | None = None,
    empty_message: str | None = None,
) -> Response:
    """Render a report to PDF and return it as an attachment Response.

    ``stats`` are the headline figures; ``facts`` the secondary label/value detail; ``footer`` the
    provenance line. ``empty_message`` replaces the table when there are no rows, so an empty
    export is a sentence rather than a lone header row.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title=title,
    )

    story: list[Flowable] = _title_block(title, subtitle, meta)
    if stats:
        story += [Spacer(1, 6 * mm), _stats_strip(stats)]
    if facts:
        story += [Spacer(1, 3 * mm), _facts_block(facts)]
    story.append(Spacer(1, 6 * mm))

    body = list(rows)
    if body:
        story.append(_data_table(header, body))
    elif empty_message:
        story.append(
            Paragraph(
                f"<font size=10 color='#64748b'><i>{escape(empty_message)}</i></font>", _cell()
            )
        )

    if footer:
        story += [
            Spacer(1, 5 * mm),
            Paragraph(
                f"<font size=8 color='#64748b'>{escape(footer)}</font>",
                ParagraphStyle("Footer", parent=_cell(), alignment=TA_RIGHT),
            ),
        ]

    doc.build(story)
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def generated_footer(generated_on: date, as_of: date, label: str) -> str:
    """The provenance line: ``label`` carries the localized "generated {x} · as of {y}" text."""
    return label.format(generated=generated_on.isoformat(), as_of=as_of.isoformat())
