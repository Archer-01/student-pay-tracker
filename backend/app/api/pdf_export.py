"""PDF rendering for the exports (reportlab), in the app's own look.

One toolkit serves all four exports so they read as the same product: the same page (A4
portrait, a header with the Ardoise mark and the teacher's name, a footer saying when it was made
and which page it is), and the same blocks the app's screens are built from (a title, a status
card, headline figures, the school share bar, the year's month tiles, a bar chart, and tables
with coloured pills).

**Fonts are bundled** (``app/assets/fonts``, SIL Open Font License): Atkinson Hyperlegible for
text and Bricolage Grotesque for titles and figures, as in the app, so a PDF looks the same on
any phone. Digits always come from Bricolage: Atkinson slashes its zero and "2026" would read
"2Ø26". Paragraphs get that through :func:`markup`; text drawn straight on the canvas through
:func:`_draw_text`. Names in Arabic script are not shaped or rendered: a known limitation.

Money keeps the backend's no-break space (U+00A0) between thousands: Atkinson has no glyph for
the narrower U+202F the browser uses.
"""

import io
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape

from fastapi import Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.paragraph import Paragraph

from app.core.i18n import format_money

# --------------------------------------------------------------------------- #
# Fonts and colours
# --------------------------------------------------------------------------- #

_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
TEXT, TEXT_BOLD = "Atkinson", "Atkinson-Bold"
DIGITS, DIGITS_BOLD = "Digits", "Digits-Bold"
DISPLAY, DISPLAY_BOLD = "Display-ExtraBold", "Display-Bold"


def _register_fonts() -> None:
    files = {
        TEXT: "AtkinsonHyperlegible-Regular.ttf",
        TEXT_BOLD: "AtkinsonHyperlegible-Bold.ttf",
        DIGITS: "BricolageGrotesque-TextRegular.ttf",
        DIGITS_BOLD: "BricolageGrotesque-TextBold.ttf",
        DISPLAY: "BricolageGrotesque-DisplayExtraBold.ttf",
        DISPLAY_BOLD: "BricolageGrotesque-DisplayBold.ttf",
    }
    for name, file in files.items():
        pdfmetrics.registerFont(TTFont(name, str(_FONTS / file)))
    # Families, so `<b>` inside a paragraph picks the bold face.
    pdfmetrics.registerFontFamily(
        TEXT, normal=TEXT, bold=TEXT_BOLD, italic=TEXT, boldItalic=TEXT_BOLD
    )
    pdfmetrics.registerFontFamily(
        DIGITS, normal=DIGITS, bold=DIGITS_BOLD, italic=DIGITS, boldItalic=DIGITS_BOLD
    )


_register_fonts()

# The app's light theme (frontend/src/index.css): paper is always light.
INK = colors.HexColor("#16201e")
MUTED = colors.HexColor("#5f6c69")
LINE = colors.HexColor("#dce3e1")
BRAND = colors.HexColor("#1f4e4a")
BRAND_MID = colors.HexColor("#8db8b2")
SCHOOL = colors.HexColor("#b98252")
SCHOOL_INK = colors.HexColor("#8a5a2f")
CHALK = colors.HexColor("#f3f6f5")

Tone = Literal["ok", "warn", "bad", "off", "brand"]
# (text, background) per tone, the app's status pairs.
TONES: dict[str, tuple[colors.Color, colors.Color]] = {
    "ok": (colors.HexColor("#1d7a4c"), colors.HexColor("#e1f3e8")),
    "warn": (colors.HexColor("#8f5300"), colors.HexColor("#fdf0d9")),
    "bad": (colors.HexColor("#ad2f27"), colors.HexColor("#fbe5e2")),
    "off": (colors.HexColor("#6b7875"), colors.HexColor("#eef1f0")),
    "brand": (BRAND, colors.HexColor("#e2eeec")),
}

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 48
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
_HEADER_HEIGHT = 78  # the top margin: the header band sits in it
_FOOTER_HEIGHT = 54

# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #

_DIGIT_RUN = re.compile(r"[0-9]+")


def markup(text: str, *, bold: bool = False) -> str:
    """Escape ``text`` for a Paragraph and set its digits in Bricolage (see the module doc)."""
    digits = DIGITS_BOLD if bold else DIGITS
    body = _DIGIT_RUN.sub(lambda m: f'<font face="{digits}">{m.group(0)}</font>', escape(text))
    return f'<font face="{TEXT_BOLD}">{body}</font>' if bold else body


def money(value: Decimal, locale: str, *, currency: bool = True) -> str:
    """Money as the app writes it: "1 234 DH", cents only when there are some."""
    text = format_money(value, locale)
    text = re.sub(r"[.,]00$", "", text)
    return f"{text} DH" if currency else text


def slugify_name(name: str) -> str:
    """An ASCII, filename-safe slug of a name (accents folded, non-alphanumerics hyphenated).

    Returns "" for names that carry no ASCII letters/digits (e.g. Arabic script) — the caller
    then falls back to an id-only filename rather than emitting an empty or non-ASCII one.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", folded).strip("-").lower()


def _style(name: str, **kw: Any) -> ParagraphStyle:
    base: dict[str, Any] = {"fontName": TEXT, "fontSize": 9.5, "leading": 13, "textColor": INK}
    return ParagraphStyle(name, **(base | kw))


BODY = _style("Body")
MUTED_TEXT = _style("Muted", textColor=MUTED)
SMALL = _style("Small", fontSize=8, leading=10.5, textColor=MUTED)
EYEBROW = _style("Eyebrow", fontName=TEXT_BOLD, fontSize=8, leading=10, textColor=BRAND)
TITLE = _style("Title", fontName=DISPLAY, fontSize=26, leading=29)
SECTION = _style("Section", fontName=DISPLAY_BOLD, fontSize=12.5, leading=16)
NUMBER = _style("Number", fontName=DIGITS)


def _draw_text(
    canv: Canvas,
    x: float,
    y: float,
    text: str,
    *,
    size: float,
    bold: bool = False,
    color: colors.Color = INK,
    align: Literal["left", "center", "right"] = "left",
) -> None:
    """Draw one line on the canvas with Bricolage digits, the way `markup` sets paragraphs."""
    runs = [
        (
            part,
            (DIGITS_BOLD if bold else DIGITS) if part.isdigit() else (TEXT_BOLD if bold else TEXT),
        )
        for part in re.split(r"([0-9]+)", text)
        if part
    ]
    width = sum(pdfmetrics.stringWidth(part, font, size) for part, font in runs)
    x -= {"left": 0, "center": width / 2, "right": width}[align]
    canv.setFillColor(color)
    for part, font in runs:
        canv.setFont(font, size)
        canv.drawString(x, y, part)
        x += pdfmetrics.stringWidth(part, font, size)


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #


def heading(eyebrow: str, title: str, sub: str | None = None) -> list[Flowable]:
    """What the page is (small, in brand green), the big title, and one grey line about it."""
    block: list[Flowable] = [
        Paragraph(markup(eyebrow.upper()), EYEBROW),
        Spacer(1, 3),
        Paragraph(escape(title), TITLE),
    ]
    if sub:
        block += [Spacer(1, 4), Paragraph(markup(sub), MUTED_TEXT)]
    return block


def section_title(text: str) -> Paragraph:
    return Paragraph(escape(text), SECTION)


def note(text: str) -> Paragraph:
    """A sentence in place of an empty table."""
    return Paragraph(markup(text), MUTED_TEXT)


def status_card(title: str, text: str | None, tone: Tone) -> Table:
    """The student page's status card: one big line in the tone's colour, one line under it."""
    ink, soft = TONES[tone]
    cells: list[Flowable] = [
        Paragraph(
            escape(title),
            _style("StatusTitle", fontName=DISPLAY, fontSize=17, leading=20, textColor=ink),
        )
    ]
    if text:
        cells += [Spacer(1, 3), Paragraph(markup(text), BODY)]
    card = Table([[cells]], colWidths=[CONTENT_WIDTH])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), soft),
                ("ROUNDEDCORNERS", [10, 10, 10, 10]),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return card


@dataclass(frozen=True)
class Fact:
    label: str
    value: str
    hint: str | None = None


def facts(items: Sequence[Fact]) -> Table:
    """A row of small label/value pairs."""
    cells = []
    for item in items:
        parts: list[Flowable] = [
            Paragraph(markup(item.label), SMALL),
            Paragraph(markup(item.value, bold=True), _style("FactValue", fontSize=11, leading=14)),
        ]
        if item.hint:
            parts.append(Paragraph(markup(item.hint), SMALL))
        cells.append(parts)
    row = Table([cells], colWidths=[CONTENT_WIDTH / len(items)] * len(items))
    row.setStyle(_plain_cells(top=0, bottom=0, left=0, right=8))
    return row


@dataclass(frozen=True)
class Figure:
    """A headline figure, as on the app's screens: a label over a big number."""

    label: str
    value: str
    hint: str | None = None
    tone: Tone | None = None


def figures(items: Sequence[Figure]) -> Table:
    """Headline figures side by side, each in its own bordered card, stacked from the top."""
    gap = 8
    width = (CONTENT_WIDTH - gap * (len(items) - 1)) / len(items)
    cards: list[Any] = []
    for item in items:
        color = TONES[item.tone][0] if item.tone else INK
        parts: list[Flowable] = [
            Paragraph(markup(item.label), SMALL),
            Spacer(1, 2),
            Paragraph(
                escape(item.value),
                _style("Figure", fontName=DISPLAY, fontSize=18, leading=21, textColor=color),
            ),
        ]
        if item.hint:
            parts += [Spacer(1, 2), Paragraph(markup(item.hint), SMALL)]
        card = Table([[parts]], colWidths=[width])
        card.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                    ("ROUNDEDCORNERS", [10, 10, 10, 10]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 11),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
                ]
            )
        )
        cards += [card, ""]
    cards.pop()
    widths: list[float] = []
    for _ in items:
        widths += [width, gap]
    widths.pop()
    row = Table([cards], colWidths=widths)
    row.setStyle(_plain_cells(valign="TOP"))
    return row


class _ShareBar(Flowable):  # type: ignore[misc]  # reportlab ships no types
    """The school share as one bar: the teacher's part in brand green, the school's in wood."""

    def __init__(self, teacher: Decimal, total: Decimal) -> None:
        super().__init__()
        self.fraction = float(teacher / total) if total > 0 else 1.0
        self.height = 8

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        return available_width, self.height

    def draw(self) -> None:
        canv, h, gap = self.canv, self.height, 2
        left = max(self.width * self.fraction - gap / 2, h)
        canv.setFillColor(BRAND)
        canv.roundRect(0, 0, left, h, h / 2, stroke=0, fill=1)
        if self.fraction < 1:
            canv.setFillColor(SCHOOL)
            canv.roundRect(left + gap, 0, self.width - left - gap, h, h / 2, stroke=0, fill=1)


def share_bar(teacher: Decimal, total: Decimal, yours: str, schools: str) -> list[Flowable]:
    """The bar, then a legend naming both parts with their amounts."""

    def legend(dot: colors.Color, text: str, align: int = 0) -> Paragraph:
        swatch = f'<font size="13" color="{dot.hexval().replace("0x", "#")}">\u2022</font>'
        return Paragraph(
            f"{swatch} {text}", _style("Legend", fontSize=8.5, textColor=MUTED, alignment=align)
        )

    row = Table(
        [[legend(BRAND, yours), legend(SCHOOL, schools, TA_RIGHT)]],
        colWidths=[CONTENT_WIDTH / 2] * 2,
    )
    row.setStyle(_plain_cells())
    return [_ShareBar(teacher, total), Spacer(1, 5), row]


def legend_amount(label: str, amount: str) -> str:
    """ "Votre part 1 234 DH" for the share legend: the label grey, the amount dark and bold."""
    return f'{markup(label)} <font color="#16201e">{markup(amount, bold=True)}</font>'


@dataclass(frozen=True)
class Tile:
    label: str  # "Sept"
    word: str  # "payé", "9 j", "à venir"…
    state: str  # a school_year TileState


class _YearTiles(Flowable):  # type: ignore[misc]  # reportlab ships no types
    """Twelve months, September to August, coloured like the student page's tiles."""

    _STYLE: dict[str, Tone | None] = {
        "paid": "ok",
        "late": "warn",
        "due": "bad",
        "away": "off",
        "upcoming": None,
        "free": "off",
        "none": None,
    }

    def __init__(self, tiles: Sequence[Tile]) -> None:
        super().__init__()
        self.tiles = tiles
        self.height = 30

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        return available_width, self.height

    def draw(self) -> None:
        canv, gap = self.canv, 4
        w = (self.width - gap * 11) / 12
        for i, tile in enumerate(self.tiles):
            x = i * (w + gap)
            tone = self._STYLE.get(tile.state)
            if tone:
                ink, soft = TONES[tone]
                canv.setFillColor(soft)
                canv.roundRect(x, 0, w, self.height, 6, stroke=0, fill=1)
            else:
                ink = TONES["off"][0]
                canv.setStrokeColor(LINE)
                canv.setLineWidth(0.8)
                if tile.state == "upcoming":
                    canv.setDash(2, 2)
                canv.roundRect(x + 0.4, 0.4, w - 0.8, self.height - 0.8, 6, stroke=1, fill=0)
                canv.setDash()
            mid = x + w / 2
            _draw_text(canv, mid, 17, tile.label, size=8, bold=True, color=ink, align="center")
            _draw_text(canv, mid, 6.5, tile.word, size=6.5, color=ink, align="center")


def year_tiles(title: str, tiles: Sequence[Tile]) -> list[Flowable]:
    return [
        Paragraph(markup(title, bold=True), _style("YearTitle", fontSize=9, textColor=MUTED)),
        Spacer(1, 4),
        _YearTiles(tiles),
    ]


@dataclass(frozen=True)
class Bar:
    label: str
    value: Decimal
    value_label: str
    highlight: bool = False
    future: bool = False


class BarChart(Flowable):  # type: ignore[misc]  # reportlab ships no types
    """Bars to scale with their amount above and the month below, the best month in brand green."""

    def __init__(self, bars: Sequence[Bar], height: float = 120) -> None:
        super().__init__()
        self.bars = bars
        self.height = height

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        return available_width, self.height

    def draw(self) -> None:
        canv, gap, base, top = self.canv, 6, 14, 12
        w = (self.width - gap * (len(self.bars) - 1)) / len(self.bars)
        peak = max((b.value for b in self.bars), default=Decimal(0))
        room = self.height - base - top
        for i, bar in enumerate(self.bars):
            x = i * (w + gap)
            h = float(bar.value / peak) * room if peak > 0 else 0
            h = max(h, 2.5)
            canv.setFillColor(
                LINE if bar.future or bar.value <= 0 else BRAND if bar.highlight else BRAND_MID
            )
            canv.roundRect(x, base, w, h, min(4, h / 2), stroke=0, fill=1)
            color = BRAND if bar.highlight else MUTED
            if bar.value > 0 and not bar.future:
                _draw_text(
                    canv,
                    x + w / 2,
                    base + h + 3.5,
                    bar.value_label,
                    size=7,
                    bold=bar.highlight,
                    color=color,
                    align="center",
                )
            _draw_text(
                canv,
                x + w / 2,
                3,
                bar.label,
                size=7.5,
                bold=bar.highlight,
                color=color,
                align="center",
            )


class Pill(Flowable):  # type: ignore[misc]  # reportlab ships no types
    """A rounded label in a status tone: "À jour", "400 DH", "9 j de retard"."""

    def __init__(self, text: str, tone: Tone, align: str = "RIGHT") -> None:
        super().__init__()
        self.text = text
        self.tone = tone
        self.hAlign = align
        self.size = 7.5
        width = sum(
            pdfmetrics.stringWidth(part, DIGITS_BOLD if part.isdigit() else TEXT_BOLD, self.size)
            for part in re.split(r"([0-9]+)", text)
        )
        self.width, self.height = width + 12, 13

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        ink, soft = TONES[self.tone]
        self.canv.setFillColor(soft)
        self.canv.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        _draw_text(
            self.canv,
            self.width / 2,
            3.7,
            self.text,
            size=self.size,
            bold=True,
            color=ink,
            align="center",
        )


@dataclass(frozen=True)
class Column:
    title: str
    width: float  # a share of the content width; the shares of a table add up to 1
    align: Literal["LEFT", "RIGHT"] = "LEFT"


def cell(
    text: str,
    *,
    sub: str | None = None,
    bold: bool = False,
    numeric: bool = False,
    muted: bool = False,
    color: colors.Color | None = None,
    align: Literal["LEFT", "RIGHT"] = "LEFT",
) -> Paragraph:
    """One table cell: a line of text, optionally with a small grey line under it."""
    ink = color or (MUTED if muted else INK)
    font = (DIGITS_BOLD if bold else DIGITS) if numeric else (TEXT_BOLD if bold else TEXT)
    body = escape(text) if numeric else markup(text)
    if sub:
        # Regular, whatever the line above it: a bold name over a grey, plain detail.
        body += f'<br/><font face="{TEXT}" size="7.5" color="#5f6c69">{markup(sub)}</font>'
    return Paragraph(
        body,
        _style(
            "Cell",
            fontName=font,
            fontSize=9,
            leading=12,
            textColor=ink,
            alignment=TA_RIGHT if align == "RIGHT" else 0,
        ),
    )


def table(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Any]],
    *,
    total: Sequence[Any] | None = None,
) -> Table:
    """A table the way the app lists things: a header over a dark rule, hairlines between rows,
    no grid. Rows are cells (`cell`, `Pill` or ""); ``total`` closes it, in bold, over a rule.
    The header repeats on every page."""
    header = [cell(c.title, muted=True, bold=True, align=c.align) for c in columns]
    data: list[Sequence[Any]] = [header, *rows]
    if total is not None:
        data.append(total)
    grid = Table(data, colWidths=[CONTENT_WIDTH * c.width for c in columns], repeatRows=1)
    style: list[Any] = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
        # Hairlines under the rows, but not under a total: it closes the table on its rule.
        ("LINEBELOW", (0, 1), (-1, -2 if total is not None else -1), 0.5, LINE),
        # Last, so it is drawn over a hairline when the table runs onto another page.
        ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
    ]
    for i, column in enumerate(columns):
        style.append(("ALIGN", (i, 0), (i, -1), column.align))
    if total is not None:
        style += [
            ("LINEABOVE", (0, -1), (-1, -1), 1, INK),
            ("TOPPADDING", (0, -1), (-1, -1), 7),
        ]
    grid.setStyle(TableStyle(style))
    return grid


def _plain_cells(
    *, top: float = 0, bottom: float = 0, left: float = 0, right: float = 0, valign: str = "TOP"
) -> TableStyle:
    return TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), valign),
            ("TOPPADDING", (0, 0), (-1, -1), top),
            ("BOTTOMPADDING", (0, 0), (-1, -1), bottom),
            ("LEFTPADDING", (0, 0), (-1, -1), left),
            ("RIGHTPADDING", (0, 0), (-1, -1), right),
        ]
    )


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def _draw_logo(canv: Canvas, x: float, y: float, size: float) -> None:
    """The Ardoise mark (components/Logo.tsx): five chalk tallies on a slate in a wooden frame."""
    k = size / 64

    def at(px: float, py: float) -> tuple[float, float]:  # SVG coordinates run downwards
        return x + px * k, y + size - py * k

    canv.setFillColor(SCHOOL)
    canv.roundRect(x, y, size, size, 15 * k, stroke=0, fill=1)
    canv.setFillColor(BRAND)
    canv.roundRect(x + 6 * k, y + 6 * k, 52 * k, 52 * k, 9 * k, stroke=0, fill=1)
    canv.setStrokeColor(CHALK)
    canv.setLineWidth(4.4 * k)
    canv.setLineCap(1)
    for (x1, y1), (x2, y2) in [
        ((21.5, 20.5), (21.2, 43.5)),
        ((28, 20), (28, 44)),
        ((34.5, 20.5), (34.8, 43.5)),
        ((41, 20.8), (40.7, 43.4)),
        ((16.5, 40), (47.5, 24.5)),
    ]:
        canv.line(*at(x1, y1), *at(x2, y2))
    canv.setLineCap(0)


def _numbered_canvas(page_label: Callable[[int, int], str]) -> type[Canvas]:
    """A canvas that holds every page back until the end, so each can say "Page 2 sur 3"."""

    class NumberedCanvas(Canvas):  # type: ignore[misc]  # reportlab ships no types
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict[str, Any]] = []

        def showPage(self) -> None:  # noqa: N802 - reportlab's name
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._pages)
            for number, state in enumerate(self._pages, start=1):
                self.__dict__.update(state)
                _draw_text(
                    self,
                    PAGE_WIDTH - MARGIN_X,
                    30,
                    page_label(number, total),
                    size=7.5,
                    color=MUTED,
                    align="right",
                )
                super().showPage()
            super().save()

    return NumberedCanvas


def render_pdf(
    story: Sequence[Flowable],
    *,
    title: str,
    teacher: str,
    footer: str,
    page_label: Callable[[int, int], str],
    filename: str,
) -> Response:
    """Lay ``story`` out on A4 pages under the header and above the footer, as an attachment."""

    def frame(canv: Canvas, _doc: Any) -> None:
        canv.saveState()
        top = PAGE_HEIGHT - 30
        _draw_logo(canv, MARGIN_X, top - 16, 20)
        canv.setFillColor(BRAND)
        canv.setFont(DISPLAY, 14)
        canv.drawString(MARGIN_X + 27, top - 11, "Ardoise")
        _draw_text(
            canv, PAGE_WIDTH - MARGIN_X, top - 10, teacher, size=9, color=MUTED, align="right"
        )
        canv.setStrokeColor(LINE)
        canv.setLineWidth(0.8)
        canv.line(MARGIN_X, top - 26, PAGE_WIDTH - MARGIN_X, top - 26)
        canv.line(MARGIN_X, 44, PAGE_WIDTH - MARGIN_X, 44)
        _draw_text(canv, MARGIN_X, 30, footer, size=7.5, color=MUTED)
        canv.restoreState()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, title=title, author=teacher, creator="Ardoise")
    # No inner padding: reportlab's default 6pt would set paragraphs in from the tables, which
    # are sized to the full content width.
    body = Frame(
        MARGIN_X,
        _FOOTER_HEIGHT,
        CONTENT_WIDTH,
        PAGE_HEIGHT - _HEADER_HEIGHT - _FOOTER_HEIGHT,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="page", frames=[body], onPage=frame)])
    doc.build(list(story), canvasmaker=_numbered_canvas(page_label))
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def gap(points: float = 14) -> Spacer:
    """Vertical space between blocks."""
    return Spacer(1, points)
