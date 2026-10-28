from dataclasses import dataclass
from typing import Literal

FileKind = Literal["pdf", "docx", "txt"]


class ParseError(Exception):
    """A file could not be turned into text. The message is safe to show to users."""


@dataclass(frozen=True, slots=True)
class Location:
    """Where a piece of text came from. Which fields are set depends on `kind`.

    PDF: `page` (1-based). DOCX: `heading` (nearest heading above, if any) and the
    paragraph range `start`..`end` (1-based, counting non-empty paragraphs and table rows).
    TXT: the line range `start`..`end` (1-based).
    """

    kind: FileKind
    page: int | None = None
    heading: str | None = None
    start: int | None = None
    end: int | None = None

    def label(self) -> str:
        """Human-readable location, worded honestly for the file type."""
        if self.kind == "pdf":
            return f"page {self.page}"
        span = f"{self.start}" if self.start == self.end else f"{self.start}-{self.end}"
        if self.kind == "txt":
            return f"line {span}" if self.start == self.end else f"lines {span}"
        paragraphs = f"paragraph {span}" if self.start == self.end else f"paragraphs {span}"
        return f"{self.heading} · {paragraphs}" if self.heading else paragraphs


@dataclass(frozen=True, slots=True)
class Segment:
    """A piece of extracted text plus its location. The chunker merges segments."""

    text: str
    location: Location
