import math
from collections import Counter
from io import BytesIO
from typing import Any

from pypdf import PageObject, PdfReader

from app.services.parsers.models import Location, ParseError, Segment

_UNREADABLE = "This PDF is corrupt or could not be read."

# A line is a heading when every run on it is set this much larger than the body text
_HEADING_RATIO = 1.15
# Longer "headings" are really large-print paragraphs, so they don't open a section
_MAX_HEADING_CHARS = 150


def parse_pdf(data: bytes) -> list[Segment]:
    """One segment per page and section that has text.

    Headings are lines set in a larger font than the body text. Each opens a section that runs
    until the next heading, across page breaks, so a section on two pages gives two segments with
    the same `section` and heading. A PDF with one font size is all one section.
    """
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("This PDF is password-protected.")
        pages = [_read_page(page) for page in reader.pages]
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(_UNREADABLE) from exc

    body_size = _body_size([run for _text, runs in pages for run in runs])
    segments: list[Segment] = []
    heading: str | None = None
    section = 0
    lines: list[str] = []

    def flush(page: int) -> None:
        if lines:
            location = Location("pdf", page=page, heading=heading)
            segments.append(Segment("\n".join(lines), location, section))
            lines.clear()

    for number, (text, runs) in enumerate(pages, start=1):
        headings = _heading_keys(runs, body_size * _HEADING_RATIO)
        # True while the section's lines so far are all heading lines (a wrapped heading)
        in_heading = False
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if _key(line) in headings:
                if in_heading and heading is not None:
                    heading = f"{heading} {line}"
                else:
                    flush(number)
                    heading, section, in_heading = line, section + 1, True
            else:
                in_heading = False
            lines.append(line)
        flush(number)

    if not segments:
        raise ParseError(
            "No text found in this PDF. It may be a scanned document; OCR is not supported."
        )
    return segments


def _read_page(page: PageObject) -> tuple[str, list[tuple[str, float]]]:
    """The page's text, and each text run with its rendered font size."""
    runs: list[tuple[str, float]] = []

    def visit(text: str, cm: Any, tm: Any, _font: Any, size: Any) -> None:
        if text:
            scale = math.hypot(tm[2], tm[3]) * math.hypot(cm[2], cm[3])
            runs.append((text, round(float(size) * scale, 1)))

    text = page.extract_text(visitor_text=visit) or ""
    return text.strip(), runs


def _body_size(runs: list[tuple[str, float]]) -> float:
    """The font size most of the document's characters are set in."""
    sizes: Counter[float] = Counter()
    for text, size in runs:
        sizes[size] += len(text.strip())
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _heading_keys(runs: list[tuple[str, float]], threshold: float) -> set[str]:
    """The page's heading lines, as `_key`s: lines whose every visible run is large."""
    keys: set[str] = set()
    line, large = "", True
    for text, size in runs:
        pieces = text.split("\n")
        for index, piece in enumerate(pieces):
            if piece.strip():
                line += piece
                large = large and size >= threshold
            if index < len(pieces) - 1:  # a line break follows this piece
                if line.strip() and large and len(line.strip()) <= _MAX_HEADING_CHARS:
                    keys.add(_key(line))
                line, large = "", True
    if line.strip() and large and len(line.strip()) <= _MAX_HEADING_CHARS:
        keys.add(_key(line))
    return keys


def _key(line: str) -> str:
    """A line with all whitespace removed, so runs and extracted text compare equal."""
    return "".join(line.split())
