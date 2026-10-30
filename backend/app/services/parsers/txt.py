import re

from charset_normalizer import from_bytes

from app.services.parsers.models import Location, ParseError, Segment

# "Q: When are you open?" or "Question: ..."; the answer lines that follow join its section
_QUESTION = re.compile(r"(?:Q|Question)\s*[:.]\s*(\S.*)", re.IGNORECASE)
_MARKDOWN_HEADING = re.compile(r"#{1,6}\s+(\S.*)")


def decode_text(data: bytes) -> str:
    match = from_bytes(data).best()
    if match is None:
        raise ParseError("Could not detect the text encoding of this file.")
    return str(match)


def section_heading(line: str) -> str | None:
    """The heading a line opens a section with: an FAQ question or a markdown heading."""
    match = _QUESTION.match(line) or _MARKDOWN_HEADING.match(line)
    return match.group(1).strip() if match else None


def parse_txt(data: bytes) -> list[Segment]:
    """One segment per non-empty line, numbered as in the original file.

    FAQ questions (`Q: ...`) and markdown headings (`# ...`) open a new section headed by
    their text; a file with neither is all one section.
    """
    if b"\x00" in data[:8192] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ParseError("This does not look like a text file.")
    text = decode_text(data) if data else ""

    segments: list[Segment] = []
    heading: str | None = None
    section = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if (opened := section_heading(line)) is not None:
            heading = opened
            section += 1
        location = Location("txt", heading=heading, start=number, end=number)
        segments.append(Segment(line, location, section))
    if not segments:
        raise ParseError("This text file is empty.")
    return segments
