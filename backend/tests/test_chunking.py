import itertools

import pytest

from app.services.chunking import Chunk, chunk_segments, estimate_tokens
from app.services.parsers import Location, Segment


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def pdf_seg(text: str, page: int) -> Segment:
    return Segment(text, Location(kind="pdf", page=page))


def txt_seg(text: str, line: int) -> Segment:
    return Segment(text, Location(kind="txt", start=line, end=line))


def docx_seg(text: str, para: int, heading: str | None = None) -> Segment:
    return Segment(text, Location(kind="docx", heading=heading, start=para, end=para))


def test_no_segments_gives_no_chunks():
    assert chunk_segments([]) == []


def test_blank_segments_are_ignored():
    assert chunk_segments([pdf_seg("   \n ", 1)]) == []


def test_short_text_is_one_chunk_with_its_location():
    seg = pdf_seg("Opening hours are 9 to 5.", 3)
    chunks = chunk_segments([seg])
    assert len(chunks) == 1
    assert chunks[0].text == "Opening hours are 9 to 5."
    assert chunks[0].location == seg.location
    assert chunks[0].index == 0


def test_estimate_tokens_grows_with_text_and_is_never_zero_for_words():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hi") == 1
    assert estimate_tokens(words(100)) > estimate_tokens(words(10))


def test_long_text_is_split_and_every_chunk_fits():
    chunks = chunk_segments([pdf_seg(words(1000), 1)], max_tokens=100, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(estimate_tokens(c.text) <= 100 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_consecutive_chunks_overlap_and_nothing_is_lost():
    text = words(1000)
    chunks = chunk_segments([pdf_seg(text, 1)], max_tokens=100, overlap_tokens=20)
    for prev, nxt in itertools.pairwise(chunks):
        assert prev.text.split()[-1] in nxt.text.split()  # shared words at the boundary
    seen = {w for c in chunks for w in c.text.split()}
    assert seen == set(text.split())


def test_zero_overlap_gives_disjoint_chunks():
    chunks = chunk_segments([pdf_seg(words(300), 1)], max_tokens=50, overlap_tokens=0)
    all_words = [w for c in chunks for w in c.text.split()]
    assert len(all_words) == len(set(all_words))


def test_oversized_word_is_split_so_no_chunk_exceeds_the_limit():
    chunks = chunk_segments([txt_seg("x" * 5000, 1)], max_tokens=10, overlap_tokens=0)
    assert len(chunks) > 1
    assert all(estimate_tokens(c.text) <= 10 for c in chunks)
    assert "".join(c.text for c in chunks) == "x" * 5000


# --- injected token counter -----------------------------------------------------------------


def test_chunker_uses_the_injected_counter_instead_of_the_estimator():
    def three_per_word(text: str) -> int:
        return 3 * len(text.split())

    chunks = chunk_segments(
        [txt_seg(words(100), 1)], max_tokens=30, overlap_tokens=0, count_tokens=three_per_word
    )
    assert len(chunks) == 10
    assert all(len(c.text.split()) == 10 for c in chunks)


def test_counter_overhead_like_cls_and_sep_is_budgeted():
    def with_special_tokens(text: str) -> int:
        return 3 * len(text.split()) + 2  # like a tokenizer that adds [CLS] and [SEP]

    chunks = chunk_segments(
        [txt_seg(words(100), 1)], max_tokens=32, overlap_tokens=0, count_tokens=with_special_tokens
    )
    assert [with_special_tokens(c.text) for c in chunks] == [32] * 10


def test_counter_overhead_must_leave_room_for_text():
    def heavy_overhead(text: str) -> int:
        return 10 + len(text.split())

    with pytest.raises(ValueError, match="overhead"):
        chunk_segments(
            [txt_seg("a b", 1)], max_tokens=10, overlap_tokens=0, count_tokens=heavy_overhead
        )


def test_a_chunk_that_counts_over_the_limit_is_split_further():
    # Counting characters, spaces included, is not additive over words, so the greedy pass
    # overshoots (5 words of 4 chars = 20, but "abcd abcd abcd abcd abcd" is 24 characters).
    chunks = chunk_segments(
        [txt_seg(" ".join(["abcd"] * 30), 1)], max_tokens=20, overlap_tokens=0, count_tokens=len
    )
    assert all(len(c.text) <= 20 for c in chunks)
    assert sum(len(c.text.split()) for c in chunks) == 30  # nothing lost or repeated


def test_oversized_word_is_split_using_the_injected_counter():
    chunks = chunk_segments(
        [txt_seg("y" * 500, 1)], max_tokens=40, overlap_tokens=0, count_tokens=len
    )
    assert all(len(c.text) <= 40 for c in chunks)
    assert "".join(c.text for c in chunks) == "y" * 500


def test_chunk_on_one_pdf_page_keeps_single_page():
    chunks = chunk_segments([pdf_seg(words(500), 4)], max_tokens=100, overlap_tokens=10)
    assert all(c.location.page == 4 and c.location.page_end is None for c in chunks)


def test_chunk_crossing_pages_gets_a_page_range():
    chunks = chunk_segments([pdf_seg("a b c", 1), pdf_seg("d e f", 2)], max_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].location.page == 1
    assert chunks[0].location.page_end == 2
    assert chunks[0].location.label() == "pages 1-2"
    assert "c" in chunks[0].text and "d" in chunks[0].text


def test_single_page_label_is_unchanged():
    assert Location(kind="pdf", page=2).label() == "page 2"


def test_docx_chunk_joins_paragraph_range_and_keeps_first_heading():
    segs = [docx_seg("one two", 1, "Refunds"), docx_seg("three four", 2, "Refunds")]
    (chunk,) = chunk_segments(segs, max_tokens=100)
    assert chunk.location.kind == "docx"
    assert chunk.location.heading == "Refunds"
    assert (chunk.location.start, chunk.location.end) == (1, 2)


def test_docx_chunk_starting_in_a_new_section_uses_that_heading():
    segs = [docx_seg(words(60, "a"), 1, "Intro"), docx_seg(words(60, "b"), 2, "Pricing")]
    chunks = chunk_segments(segs, max_tokens=60, overlap_tokens=0)
    assert chunks[0].location.heading == "Intro"
    assert chunks[-1].location.heading == "Pricing"


def test_txt_chunk_joins_line_range():
    segs = [txt_seg("alpha beta", 1), txt_seg("gamma delta", 2), txt_seg("epsilon", 3)]
    (chunk,) = chunk_segments(segs, max_tokens=100)
    assert (chunk.location.start, chunk.location.end) == (1, 3)
    assert chunk.location.label() == "lines 1-3"


def test_chunks_only_cover_the_segments_they_contain():
    segs = [txt_seg(words(40, "a"), 1), txt_seg(words(40, "b"), 2), txt_seg(words(40, "c"), 3)]
    chunks = chunk_segments(segs, max_tokens=60, overlap_tokens=0)
    first, last = chunks[0], chunks[-1]
    assert first.location.start == 1
    assert last.location.end == 3
    assert last.location.start is not None and last.location.start > 1


def test_original_line_breaks_inside_a_segment_are_kept():
    (chunk,) = chunk_segments([pdf_seg("line one\nline two", 1)])
    assert chunk.text == "line one\nline two"


def test_chunk_is_immutable_value():
    chunk = chunk_segments([pdf_seg("hello", 1)])[0]
    assert isinstance(chunk, Chunk)
    with pytest.raises(AttributeError):
        chunk.text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(("max_tokens", "overlap"), [(0, 0), (10, 10), (10, 11), (10, -1)])
def test_invalid_sizes_are_rejected(max_tokens: int, overlap: int):
    with pytest.raises(ValueError):
        chunk_segments([pdf_seg("a", 1)], max_tokens=max_tokens, overlap_tokens=overlap)
