import itertools
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.services.parsers import Location, Segment

DEFAULT_MAX_TOKENS = 350
DEFAULT_OVERLAP_TOKENS = 50

TokenCounter = Callable[[str], int]

_WORD = re.compile(r"\S+")
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable piece of a document: text plus where in the file it came from."""

    text: str
    location: Location
    index: int


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (about 4 characters per word-piece) that needs no tokenizer.

    Fine for prose; it badly under-counts codes, digits and punctuation, so use the embedding
    model's own counter wherever a hard input limit matters.
    """
    return sum(max(1, math.ceil(len(m.group()) / _CHARS_PER_TOKEN)) for m in _WORD.finditer(text))


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
        page_end = high if high != low else None
        return Location(kind="pdf", page=low, page_end=page_end, heading=first.heading)
    starts = [s for loc in locations if (s := loc.start) is not None]
    ends = [e for loc in locations if (e := loc.end) is not None]
    return Location(kind=first.kind, heading=first.heading, start=min(starts), end=max(ends))


def chunk_segments(
    segments: list[Segment],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    count_tokens: TokenCounter = estimate_tokens,
) -> list[Chunk]:
    """Turn located segments into chunks of at most `max_tokens`, as measured by `count_tokens`
    (pass the embedder's own counter so the limit is real, not estimated).

    Structure comes first: each section (consecutive segments with the same `section`, such as
    a heading and its paragraphs, or an FAQ question and its answer) becomes one chunk when it
    fits. Only a section over the limit is split into token windows, which stay inside it and
    share about `overlap_tokens` so an answer split across a window boundary is still found.

    A chunk's location covers just the segments it holds, under its section's heading: a page
    range for PDFs, a paragraph range for DOCX and a line range for TXT.

    No chunk is ever emitted over the limit: a word too long to fit is split into pieces, and
    any chunk that the word-by-word budget let through but the counter rejects is cut down.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens must be at least 0 and less than max_tokens")

    # Tokenizers add fixed tokens to every input (like [CLS] and [SEP]); that overhead is paid
    # once per chunk, not per word, so measure it on empty text and take it off the budget.
    overhead = count_tokens("")
    budget = max_tokens - overhead
    if budget <= 0:
        raise ValueError(
            f"token counter overhead ({overhead}) leaves no room within max_tokens={max_tokens}"
        )

    pieces: list[tuple[str, Location]] = []
    for _section, group in itertools.groupby(segments, key=lambda s: s.section):
        filled = [s for s in group if s.text.strip()]
        if not filled:
            continue
        text = "\n".join(s.text.strip() for s in filled)
        if count_tokens(text) <= max_tokens:
            pieces.append((text, _merge_locations([s.location for s in filled])))
        else:
            pieces += _token_windows(filled, max_tokens, overlap_tokens, count_tokens, overhead)
    return [
        Chunk(text=text, location=location, index=index)
        for index, (text, location) in enumerate(pieces)
    ]


def _token_windows(
    segments: list[Segment],
    max_tokens: int,
    overlap_tokens: int,
    count_tokens: TokenCounter,
    overhead: int,
) -> list[tuple[str, Location]]:
    """Overlapping windows of whole words over segments too long to be one chunk."""
    budget = max_tokens - overhead
    units = _split_into_units(segments, count_tokens, overhead, budget)

    chunks: list[tuple[str, Location]] = []
    begin = 0
    while begin < len(units):
        end, total = begin, 0
        while end < len(units) and (end == begin or total + units[end].tokens <= budget):
            total += units[end].tokens
            end += 1
        end, text, location = _fit_window(segments, units, begin, end, max_tokens, count_tokens)
        chunks.append((text, location))
        if end == len(units):
            break
        # Step back from the end to carry the overlap, always moving forward overall.
        begin_next, carried = end, 0
        while begin_next - 1 > begin and carried + units[begin_next - 1].tokens <= overlap_tokens:
            begin_next -= 1
            carried += units[begin_next].tokens
        begin = begin_next
    return chunks


def _split_into_units(
    segments: list[Segment], count_tokens: TokenCounter, overhead: int, budget: int
) -> list[_Unit]:
    units: list[_Unit] = []
    for index, segment in enumerate(segments):
        for match in _WORD.finditer(segment.text):
            units.extend(
                _word_units(
                    index, segment.text, match.start(), match.end(), count_tokens, overhead, budget
                )
            )
    return units


def _word_units(
    segment: int,
    text: str,
    start: int,
    end: int,
    count_tokens: TokenCounter,
    overhead: int,
    budget: int,
) -> list[_Unit]:
    """One unit for the word, or, if it can't fit in a chunk by itself, halves of it."""
    tokens = max(1, count_tokens(text[start:end]) - overhead)
    if tokens <= budget or end - start <= 1:
        return [_Unit(segment, start, end, tokens)]
    middle = (start + end) // 2
    return _word_units(segment, text, start, middle, count_tokens, overhead, budget) + _word_units(
        segment, text, middle, end, count_tokens, overhead, budget
    )


def _fit_window(
    segments: list[Segment],
    units: list[_Unit],
    begin: int,
    end: int,
    max_tokens: int,
    count_tokens: TokenCounter,
) -> tuple[int, str, Location]:
    """Build the chunk for units[begin:end], shrinking it until the counter accepts it."""
    while True:
        text, location = _assemble(segments, units[begin:end])
        used = count_tokens(text)
        if used <= max_tokens:
            return end, text, location
        size = end - begin
        if size == 1:
            raise ValueError(f"cannot fit {text!r} within max_tokens={max_tokens}")
        end = begin + max(1, min(size - 1, int(size * max_tokens / used)))


def _assemble(segments: list[Segment], window: list[_Unit]) -> tuple[str, Location]:
    parts: list[str] = []
    locations: list[Location] = []
    for segment_index in dict.fromkeys(u.segment for u in window):
        covered = [u for u in window if u.segment == segment_index]
        parts.append(segments[segment_index].text[covered[0].start : covered[-1].end])
        locations.append(segments[segment_index].location)
    return "\n".join(parts), _merge_locations(locations)
