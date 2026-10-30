from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.parsers.models import Location, ParseError, Segment

_HEADING_STYLES = ("heading", "title")


def _is_heading(paragraph: Paragraph) -> bool:
    style = paragraph.style
    name = (style.name or "") if style is not None else ""
    return name.lower().startswith(_HEADING_STYLES)


def parse_docx(data: bytes) -> list[Segment]:
    """One segment per non-empty paragraph or table row, tagged with the nearest heading.

    Headings are tracked as context and also emitted as segments, so a question about a
    heading's wording can still match. Each heading opens a new section, which takes in the
    paragraphs and table rows under it.
    """
    try:
        doc = Document(BytesIO(data))
        blocks = list(doc.iter_inner_content())
    except Exception as exc:
        raise ParseError("This DOCX file is corrupt or could not be read.") from exc

    segments: list[Segment] = []
    heading: str | None = None
    section = 0
    count = 0

    def add(text: str) -> None:
        nonlocal count
        count += 1
        location = Location("docx", heading=heading, start=count, end=count)
        segments.append(Segment(text, location, section))

    for block in blocks:
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            if _is_heading(block):
                heading = text
                section += 1
            add(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells]
                # Merged cells repeat in python-docx; drop adjacent duplicates and blanks.
                unique = [c for i, c in enumerate(cells) if c and (i == 0 or c != cells[i - 1])]
                if unique:
                    add(" | ".join(unique))

    if not segments:
        raise ParseError("No text found in this DOCX file.")
    return segments
