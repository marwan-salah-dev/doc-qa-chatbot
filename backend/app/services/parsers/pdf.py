from io import BytesIO

from pypdf import PdfReader

from app.services.parsers.models import Location, ParseError, Segment

_UNREADABLE = "This PDF is corrupt or could not be read."


def parse_pdf(data: bytes) -> list[Segment]:
    """One segment per page that has text."""
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("This PDF is password-protected.")
        segments = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                segments.append(Segment(text, Location("pdf", page=index)))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(_UNREADABLE) from exc

    if not segments:
        raise ParseError(
            "No text found in this PDF. It may be a scanned document; OCR is not supported."
        )
    return segments
