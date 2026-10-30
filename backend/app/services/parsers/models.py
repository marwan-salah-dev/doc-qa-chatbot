from dataclasses import dataclass
from typing import Literal

FileKind = Literal["pdf", "docx", "txt"]


class ParseError(Exception):
    """A file could not be turned into text. The message is safe to show to users."""


@dataclass(frozen=True, slots=True)
class Location:
    """Where a piece of text came from. Which fields are set depends on `kind`.

    PDF: `page` (1-based), plus `page_end` when a chunk spans several pages.
    DOCX: the paragraph range `start`..`end` (1-based, counting non-empty paragraphs and table
    rows).
    TXT: the line range `start`..`end` (1-based).
    Any kind: `heading`, the section heading in force (nearest heading above), if there is one.
    """

    kind: FileKind
    page: int | None = None
    heading: str | None = None
    start: int | None = None
    end: int | None = None
    page_end: int | None = None

    def label(self) -> str:
        """Human-readable location, worded honestly for the file type."""
        if self.kind == "pdf":
            if self.page_end is not None and self.page_end != self.page:
                where = f"pages {self.page}-{self.page_end}"
            else:
                where = f"page {self.page}"
        else:
            span = f"{self.start}" if self.start == self.end else f"{self.start}-{self.end}"
            unit = "line" if self.kind == "txt" else "paragraph"
            where = f"{unit} {span}" if self.start == self.end else f"{unit}s {span}"
        return f"{self.heading} · {where}" if self.heading else where


@dataclass(frozen=True, slots=True)
class Segment:
    """A piece of extracted text plus its location. The chunker merges segments.

    `section` numbers the document's structural sections (a heading and what follows it, or an
    FAQ question and its answer). Consecutive segments with the same number belong together, and
    the chunker never merges across a change. A document with no structure is all section 0.
    """

    text: str
    location: Location
    section: int = 0
