from pathlib import PurePath

from app.services.parsers.docx import parse_docx
from app.services.parsers.models import FileKind, Location, ParseError, Segment
from app.services.parsers.pdf import parse_pdf
from app.services.parsers.txt import parse_txt

_PARSERS = {"pdf": parse_pdf, "docx": parse_docx, "txt": parse_txt}

__all__ = [
    "FileKind",
    "Location",
    "ParseError",
    "Segment",
    "file_kind",
    "parse_document",
]


def file_kind(filename: str) -> FileKind:
    """Map a filename to a supported kind by extension, or raise ParseError."""
    suffix = PurePath(filename).suffix.lower().lstrip(".")
    if suffix not in _PARSERS:
        raise ParseError("Unsupported file type. Upload a PDF, DOCX or TXT file.")
    return suffix  # type: ignore[return-value]


def parse_document(filename: str, data: bytes) -> list[Segment]:
    """Extract located text segments from an uploaded file. Raises ParseError on failure."""
    return _PARSERS[file_kind(filename)](data)
