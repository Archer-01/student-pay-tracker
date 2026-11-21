"""Reading the exported PDFs back as text, for the tests that assert on them."""

import io

from pypdf import PdfReader


def pdf_text(raw: bytes) -> str:
    """Visible text of a PDF, lowercased with whitespace collapsed, so exports can be asserted on.

    Read with pypdf rather than by grepping the content stream: the PDFs embed their fonts, so
    the stream holds glyph codes, not text. ``split()`` also folds the no-break spaces French
    typography puts inside numbers and before punctuation into plain ones.
    """
    return " ".join(pdf_pages(raw))


def pdf_pages(raw: bytes) -> list[str]:
    """Each page's text, as `pdf_text` reads it."""
    reader = PdfReader(io.BytesIO(raw))
    return [" ".join((page.extract_text() or "").split()).lower() for page in reader.pages]
