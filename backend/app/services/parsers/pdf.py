import math
import re
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
# Bold headings at body size are stricter: short, and not a bold sentence ("Refunds are final.")
_MAX_BOLD_HEADING_CHARS = 100
_SENTENCE_END = (".", ",", ";")
# Weight words in font names, after any subset prefix ("ABCDEF+Arial-BoldMT")
_BOLD_NAME = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
_BOLD_WEIGHT = 600

# (text, rendered font size, bold)
_Run = tuple[str, float, bool]


def parse_pdf(data: bytes) -> list[Segment]:
    """One segment per page and section that has text.

    Headings are lines set in a larger font than the body text, or lines set entirely in bold
    when the body is not (many real PDFs set headings bold at the body size). Each opens a
    section that runs until the next heading, across page breaks, so a section on two pages gives
    two segments with the same `section` and heading. A PDF with one font size and weight is all
    one section. Not detected: "fake bold" (outlined text, render mode 2) and headings that differ
    from the body only by colour or numbering.
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

    body_size, body_bold = _body_style([run for _text, runs in pages for run in runs])
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
        headings = _heading_keys(runs, body_size * _HEADING_RATIO, bold_counts=not body_bold)
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


def _read_page(page: PageObject) -> tuple[str, list[_Run]]:
    """The page's text, and each text run with its rendered font size and boldness."""
    runs: list[_Run] = []

    def visit(text: str, cm: Any, tm: Any, font: Any, size: Any) -> None:
        if text:
            scale = math.hypot(tm[2], tm[3]) * math.hypot(cm[2], cm[3])
            runs.append((text, round(float(size) * scale, 1), _is_bold(font)))

    text = page.extract_text(visitor_text=visit) or ""
    return text.strip(), runs


def _is_bold(font: Any) -> bool:
    """Whether a pypdf font dictionary is a bold face, by name or by declared weight."""
    try:
        if font is None:
            return False
        if _BOLD_NAME.search(str(font.get("/BaseFont", "")).split("+")[-1]):
            return True
        descriptor = font.get("/FontDescriptor")
        descriptor = descriptor.get_object() if descriptor is not None else None
        weight = descriptor.get("/FontWeight") if descriptor is not None else None
        return weight is not None and float(weight) >= _BOLD_WEIGHT
    except Exception:  # a malformed font dictionary only means "not known to be bold"
        return False


def _body_style(runs: list[_Run]) -> tuple[float, bool]:
    """The font size and boldness most of the document's characters are set in."""
    styles: Counter[tuple[float, bool]] = Counter()
    for text, size, bold in runs:
        styles[(size, bold)] += len(text.strip())
    return styles.most_common(1)[0][0] if styles else (0.0, False)


def _heading_keys(runs: list[_Run], threshold: float, *, bold_counts: bool) -> set[str]:
    """The page's heading lines, as `_key`s: lines whose every visible run is large, or (when
    `bold_counts`, i.e. the body isn't bold) short lines whose every visible run is bold."""
    keys: set[str] = set()

    def finish(line: str, large: bool, bold: bool) -> None:
        line = line.strip()
        if not line:
            return
        if (large and len(line) <= _MAX_HEADING_CHARS) or (
            bold_counts
            and bold
            and len(line) <= _MAX_BOLD_HEADING_CHARS
            and not line.endswith(_SENTENCE_END)
        ):
            keys.add(_key(line))

    line, large, bold = "", True, True
    for text, size, run_bold in runs:
        pieces = text.split("\n")
        for index, piece in enumerate(pieces):
            if piece.strip():
                line += piece
                large = large and size >= threshold
                bold = bold and run_bold
            if index < len(pieces) - 1:  # a line break follows this piece
                finish(line, large, bold)
                line, large, bold = "", True, True
    finish(line, large, bold)
    return keys


def _key(line: str) -> str:
    """A line with all whitespace removed, so runs and extracted text compare equal."""
    return "".join(line.split())
