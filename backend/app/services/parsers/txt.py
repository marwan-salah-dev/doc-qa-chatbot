from charset_normalizer import from_bytes

from app.services.parsers.models import Location, ParseError, Segment


def decode_text(data: bytes) -> str:
    match = from_bytes(data).best()
    if match is None:
        raise ParseError("Could not detect the text encoding of this file.")
    return str(match)


def parse_txt(data: bytes) -> list[Segment]:
    """One segment per non-empty line, numbered as in the original file."""
    if b"\x00" in data[:8192] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ParseError("This does not look like a text file.")
    text = decode_text(data) if data else ""

    segments = [
        Segment(line.strip(), Location("txt", start=number, end=number))
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    if not segments:
        raise ParseError("This text file is empty.")
    return segments
