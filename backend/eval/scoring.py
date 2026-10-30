"""Simple, explainable checks: no LLM judge. Pure functions, so they are unit tested."""

import math
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.services.parsers import Location
from app.services.rag import DoneEvent, strip_citation_markers
from app.services.vectorstore import SearchHit
from eval.dataset import ExpectedSource, GoldenQuestion


class Located(Protocol):
    """A retrieved chunk or a cited source: anything with a file name and a location."""

    @property
    def filename(self) -> str: ...

    @property
    def location(self) -> Location: ...


def is_expected(item: Located, expected: Iterable[ExpectedSource]) -> bool:
    return any(
        item.filename == source.file and item.location.heading == source.section
        for source in expected
    )


def first_hit_rank(
    hits: Sequence[SearchHit], expected: Sequence[ExpectedSource], min_score: float = 0.0
) -> int | None:
    """1-based rank of the first hit in an expected section (scoring at least `min_score`)."""
    for rank, hit in enumerate(hits, start=1):
        if hit.score >= min_score and is_expected(hit.chunk, expected):
            return rank
    return None


def best_expected_score(
    hits: Sequence[SearchHit], expected: Sequence[ExpectedSource]
) -> float | None:
    scores = [hit.score for hit in hits if is_expected(hit.chunk, expected)]
    return max(scores) if scores else None


def hit_rate(ranks: Sequence[int | None], k: int) -> float | None:
    """Share of questions whose expected section was in the top `k`."""
    if not ranks:
        return None
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


@dataclass(frozen=True, slots=True)
class Distribution:
    count: int
    min: float
    median: float
    max: float


def score_distribution(scores: Sequence[float]) -> Distribution | None:
    if not scores:
        return None
    return Distribution(len(scores), min(scores), statistics.median(scores), max(scores))


@dataclass(frozen=True, slots=True)
class Recommendation:
    threshold: float
    lowest_answerable: float
    highest_off_topic: float
    margin_below_answerable: float  # how far the lowest answerable top score sits above it
    margin_above_off_topic: float  # how far it sits above the highest off-topic score
    overlap: bool


def recommend_threshold(answerable: Sequence[float], off_topic: Sequence[float]) -> Recommendation:
    """A RAG_MIN_SCORE from each question's top retrieval score.

    With a clean gap, the middle of it, so both sides get the same margin. When the groups
    overlap, just under the lowest answerable score: refusing a real question is worse than
    letting an off-topic one through, because the LLM still refuses what the sources don't cover.
    """
    if not answerable or not off_topic:
        raise ValueError("need top scores for both answerable and off-topic questions")
    low, high = min(answerable), max(off_topic)
    overlap = high >= low
    if overlap:
        threshold = round(math.floor(low * 100) / 100 - 0.01, 2)
    else:
        threshold = round((low + high) / 2, 2)
    return Recommendation(threshold, low, high, low - threshold, threshold - high, overlap)


def compare_with_previous(
    current: Mapping[str, float | None], previous: Mapping[str, float | None] | None
) -> dict[str, float | None] | None:
    """Change in each metric since the previous run; `None` for a metric it didn't have."""
    if previous is None:
        return None
    deltas: dict[str, float | None] = {}
    for key, value in current.items():
        before = previous.get(key)
        deltas[key] = None if value is None or before is None else value - before
    return deltas


# --- answers --------------------------------------------------------------------------------


def _normalize(answer: str) -> str:
    text = strip_citation_markers(answer)
    text = text.replace("\N{NO-BREAK SPACE}", " ").replace("\N{NARROW NO-BREAK SPACE}", " ")
    return text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")


def missing_facts(answer: str, facts: Sequence[str]) -> list[str]:
    """The fact patterns the answer doesn't contain (case-insensitive, citation markers removed)."""
    text = _normalize(answer)
    return [fact for fact in facts if not re.search(fact, text, re.IGNORECASE)]


def cited_correctly(
    citations: Sequence[Located], expected: Sequence[ExpectedSource]
) -> tuple[bool, bool]:
    """(an expected file is cited, an expected file *and section* is cited)."""
    files = {source.file for source in expected}
    file_ok = any(citation.filename in files for citation in citations)
    return file_ok, any(is_expected(citation, expected) for citation in citations)


@dataclass(frozen=True, slots=True)
class AnswerScore:
    passed: bool
    refused: bool
    refused_by: Literal["threshold", "llm"] | None
    missing_facts: list[str]
    cited_file_ok: bool
    cited_section_ok: bool
    uncited: bool


def score_answer(question: GoldenQuestion, done: DoneEvent, reached_llm: bool) -> AnswerScore:
    """Pass: an answerable question gets every fact with a citation to an expected file; an
    unanswerable one is refused. `reached_llm` tells a threshold refusal from the model's."""
    refused_by = ("llm" if reached_llm else "threshold") if done.refused else None
    missing = [] if done.refused else missing_facts(done.answer, question.facts)
    file_ok, section_ok = cited_correctly(done.citations, question.sources)
    if question.kind == "unanswerable":
        passed = done.refused
    else:
        passed = not done.refused and not missing and file_ok
    return AnswerScore(
        passed=passed,
        refused=done.refused,
        refused_by=refused_by,
        missing_facts=missing,
        cited_file_ok=file_ok,
        cited_section_ok=section_ok,
        uncited=done.uncited,
    )
