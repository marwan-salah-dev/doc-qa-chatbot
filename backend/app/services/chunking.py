import math
import re
from dataclasses import dataclass

from app.services.parsers import Location, Segment

DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50

_WORD = re.compile(r"\S+")
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable piece of a document: text plus where in the file it came from."""

    text: str
    location: Location
    index: int


def _word_tokens(word: str) -> int:
    return max(1, math.ceil(len(word) / _CHARS_PER_TOKEN))


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (about 4 characters per token) that needs no tokenizer download."""
    return sum(_word_tokens(m.group()) for m in _WORD.finditer(text))


@dataclass(frozen=True, slots=True)
class _Unit:
    segment: int
    start: int
    end: int
    tokens: int


def _merge_locations(locations: list[Location]) -> Location:
    first = locations[0]
    if first.kind == "pdf":
        pages = [p for loc in locations if (p := loc.page) is not None]
        low, high = min(pages), max(pages)
        return Location(kind="pdf", page=low, page_end=high if high != low else None)
    starts = [s for loc in locations if (s := loc.start) is not None]
    ends = [e for loc in locations if (e := loc.end) is not None]
    return Location(kind=first.kind, heading=first.heading, start=min(starts), end=max(ends))


def chunk_segments(
    segments: list[Segment],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Merge located segments into overlapping chunks of at most `max_tokens` (estimated).

    A chunk's location covers every segment it touches: a page range for PDFs, a paragraph or
    line range for DOCX and TXT (with the heading in force where the chunk starts). Consecutive
    chunks share about `overlap_tokens` so an answer split across a boundary is still found.
    A single word longer than `max_tokens` becomes its own oversized chunk rather than looping.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens must be at least 0 and less than max_tokens")

    units = [
        _Unit(i, m.start(), m.end(), _word_tokens(m.group()))
        for i, seg in enumerate(segments)
        for m in _WORD.finditer(seg.text)
    ]

    chunks: list[Chunk] = []
    begin = 0
    while begin < len(units):
        end, total = begin, 0
        while end < len(units) and (end == begin or total + units[end].tokens <= max_tokens):
            total += units[end].tokens
            end += 1
        chunks.append(_build_chunk(segments, units[begin:end], len(chunks)))
        if end == len(units):
            break
        # Step back from the end to carry the overlap, always moving forward overall.
        begin_next, carried = end, 0
        while begin_next - 1 > begin and carried + units[begin_next - 1].tokens <= overlap_tokens:
            begin_next -= 1
            carried += units[begin_next].tokens
        begin = begin_next
    return chunks


def _build_chunk(segments: list[Segment], window: list[_Unit], index: int) -> Chunk:
    parts: list[str] = []
    locations: list[Location] = []
    for segment_index in dict.fromkeys(u.segment for u in window):
        covered = [u for u in window if u.segment == segment_index]
        parts.append(segments[segment_index].text[covered[0].start : covered[-1].end])
        locations.append(segments[segment_index].location)
    return Chunk(text="\n".join(parts), location=_merge_locations(locations), index=index)
