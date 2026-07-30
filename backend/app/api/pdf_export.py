"""PDF responses for exports (tabular reports rendered with reportlab).

Uses reportlab's built-in Helvetica, which covers Latin-1 (including French accents). Arabic-script
names are not shaped/rendered — a known limitation; the CSV path previously relied on Excel + a BOM.
"""

import io
from collections.abc import Iterable, Sequence

from fastapi import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.paragraph import Paragraph

_HEADER_BG = colors.HexColor("#334155")  # slate-700
_GRID = colors.HexColor("#cbd5e1")  # slate-300


def render_table_pdf(
    title: str, header: Sequence[str], rows: Iterable[Sequence[str]], filename: str
) -> Response:
    """Render a titled table to a PDF and return it as an attachment Response."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=title,
    )

    styles = getSampleStyleSheet()
    data = [list(header)] + [list(row) for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    doc.build([Paragraph(title, styles["Title"]), Spacer(1, 8 * mm), table])

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
