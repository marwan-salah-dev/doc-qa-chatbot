"""The eval package: the golden dataset, its scoring, results files and the answer runner."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from app.services.chunking import chunk_segments
from app.services.llm import FakeChat, LLMRateLimitError
from app.services.parsers import Location, parse_document
from app.services.parsers.models import FileKind
from app.services.rag import NOT_FOUND, DoneEvent, RagService, Source
from app.services.vectorstore import ChromaVectorStore, SearchHit, StoredChunk
from eval.answers import Estimate, run_questions
from eval.dataset import (
    DatasetError,
    ExpectedSource,
    GoldenQuestion,
    load_questions,
    parse_questions,
)
from eval.index import DEMO_WORKSPACE_ID, index_demo_docs
from eval.results import load_previous, save_results
from eval.scoring import (
    cited_correctly,
    compare_with_previous,
    first_hit_rank,
    hit_rate,
    missing_facts,
    recommend_threshold,
    score_answer,
    score_distribution,
)
from scripts.seed_demo import DEMO_DATA_DIR, DEMO_FILES

pytestmark = pytest.mark.anyio

PDF, DOCX, TXT = DEMO_FILES
HOURS = ExpectedSource(PDF, "1. Opening hours")
FEE = ExpectedSource(TXT, "Can I cancel or move my appointment?")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- the golden dataset -------------------------------------------------------------------

QUESTIONS = load_questions()
ENGLISH_ANSWERABLE = [q for q in QUESTIONS if q.kind == "answerable" and q.language == "en"]
NON_ENGLISH = [q for q in QUESTIONS if q.style == "non-english"]

STOPWORDS = {
    "a", "an", "and", "are", "can", "do", "does", "for", "how", "i", "in", "is", "it", "my",
    "of", "on", "or", "the", "to", "what", "when", "where", "which", "who", "you", "your",
}  # fmt: skip


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS and len(w) >= 4}


def shares_a_word(question: str, heading: str) -> set[str]:
    """Words of the question that are, or start, a heading word (so "open" ~ "opening")."""
    heading_words = content_words(heading)
    return {
        word
        for word in content_words(question)
        if any(h.startswith(word) or word.startswith(h) for h in heading_words)
    }


def demo_sections() -> set[ExpectedSource]:
    found: set[ExpectedSource] = set()
    for filename in DEMO_FILES:
        segments = parse_document(filename, (DEMO_DATA_DIR / filename).read_bytes())
        for chunk in chunk_segments(segments):
            if chunk.location.heading is not None:
                found.add(ExpectedSource(filename, chunk.location.heading))
    return found


def test_golden_file_has_every_kind_style_and_language():
    assert 30 <= len(QUESTIONS) <= 40
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS)
    assert {q.kind for q in QUESTIONS} == {"answerable", "followup", "unanswerable"}
    assert {q.topic for q in QUESTIONS if q.kind == "unanswerable"} == {"off", "in-domain"}


def test_at_least_half_the_english_answerable_questions_are_paraphrased():
    paraphrased = [q for q in ENGLISH_ANSWERABLE if q.style == "paraphrased"]
    assert len(paraphrased) * 2 >= len(ENGLISH_ANSWERABLE)


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q.style == "paraphrased"])
def test_paraphrased_questions_avoid_their_section_heading_words(question: GoldenQuestion):
    for source in question.sources:
        assert not shares_a_word(question.question, source.section), source.section


def test_non_english_questions_are_two_per_language_and_never_calibrated_or_sent_to_the_llm():
    assert sorted(q.language for q in NON_ENGLISH) == ["ar", "ar", "es", "es", "fr", "fr"]
    for question in NON_ENGLISH:
        assert not question.calibrated
        assert not question.answer_eval
    for question in (q for q in NON_ENGLISH if q.language == "ar"):
        assert re.search("[؀-ۿ]", question.question)


def test_every_expected_source_is_a_real_section_of_the_demo_files():
    sections = demo_sections()
    for question in QUESTIONS:
        for source in question.sources:
            assert source in sections, f"{question.id}: {source}"


def test_answer_subset_is_small_and_mixes_answers_and_refusals():
    subset = [q for q in QUESTIONS if q.answer_eval]
    assert 6 <= len(subset) <= 10
    assert {q.kind for q in subset} == {"answerable", "followup", "unanswerable"}
    assert {q.topic for q in subset if q.kind == "unanswerable"} == {"off", "in-domain"}


def test_followups_retrieve_with_their_standalone_question():
    followup = next(q for q in QUESTIONS if q.kind == "followup")
    assert followup.history
    assert followup.retrieval_query == followup.standalone != followup.question


def entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "q1",
        "kind": "answerable",
        "style": "literal",
        "question": "When are you open?",
        "facts": ["9 am"],
        "sources": [{"file": PDF, "section": "1. Opening hours"}],
    }
    return {**base, **overrides}


@pytest.mark.parametrize(
    "bad",
    [
        entry(kind="maybe"),
        entry(style="formal"),
        entry(facts=[]),
        entry(sources=[]),
        entry(facts=["(unclosed"]),
        entry(kind="unanswerable", topic="off"),  # unanswerable with facts and sources
        entry(kind="unanswerable", facts=[], sources=[]),  # no topic
        entry(kind="followup"),  # no history or standalone
        entry(style="non-english"),  # no language
        entry(style="non-english", language="de"),
        entry(style="non-english", language="ar", answer_eval=True),
        entry(language="fr"),  # a language other than English must be style non-english
    ],
)
def test_invalid_entries_are_rejected(bad: dict[str, object]):
    with pytest.raises(DatasetError):
        parse_questions({"question": [bad]})


def test_duplicate_ids_are_rejected():
    with pytest.raises(DatasetError, match="duplicate"):
        parse_questions({"question": [entry(), entry()]})


# --- retrieval scoring ----------------------------------------------------------------------


def hit(filename: str, heading: str | None, score: float) -> SearchHit:
    kind = cast(FileKind, filename.rsplit(".", 1)[-1])
    location = (
        Location(kind, page=1, heading=heading)
        if kind == "pdf"
        else Location(kind, heading=heading, start=1, end=1)
    )
    return SearchHit(StoredChunk("doc", filename, 0, "text", location), score)


def test_first_hit_rank_is_one_based_and_any_expected_source_counts():
    hits = [hit(DOCX, "Treatments and prices", 0.8), hit(TXT, FEE.section, 0.7)]

    assert first_hit_rank(hits, [HOURS, FEE]) == 2
    assert first_hit_rank(hits, [HOURS]) is None


def test_first_hit_rank_ignores_hits_below_the_threshold():
    hits = [hit(PDF, HOURS.section, 0.5)]

    assert first_hit_rank(hits, [HOURS], min_score=0.5) == 1
    assert first_hit_rank(hits, [HOURS], min_score=0.6) is None


def test_hit_rate_counts_ranks_within_k():
    assert hit_rate([1, 3, None, 2], k=2) == 0.5
    assert hit_rate([], k=3) is None


def test_score_distribution():
    dist = score_distribution([0.5, 0.2, 0.9])
    assert dist is not None
    assert (dist.count, dist.min, dist.median, dist.max) == (3, 0.2, 0.5, 0.9)
    assert score_distribution([]) is None


def test_recommend_threshold_takes_the_middle_of_a_clean_gap():
    rec = recommend_threshold(answerable=[0.70, 0.62, 0.81], off_topic=[0.40, 0.48])

    assert not rec.overlap
    assert rec.threshold == 0.55
    assert rec.lowest_answerable == 0.62
    assert rec.highest_off_topic == 0.48
    assert rec.margin_below_answerable == pytest.approx(0.07)
    assert rec.margin_above_off_topic == pytest.approx(0.07)


def test_recommend_threshold_errs_low_when_the_groups_overlap():
    rec = recommend_threshold(answerable=[0.55, 0.70], off_topic=[0.40, 0.58])

    assert rec.overlap
    # Just under the lowest answerable score: the LLM's refusal is the backstop
    assert rec.threshold == 0.54
    assert rec.margin_below_answerable == pytest.approx(0.01)
    assert rec.margin_above_off_topic < 0


def test_recommend_threshold_needs_both_groups():
    with pytest.raises(ValueError):
        recommend_threshold(answerable=[], off_topic=[0.3])


def test_compare_with_previous_gives_deltas():
    current = {"hit@1": 0.8, "hit@3": 1.0, "new": 0.5}
    previous = {"hit@1": 0.7, "hit@3": 1.0}

    assert compare_with_previous(current, None) is None
    deltas = compare_with_previous(current, previous)
    assert deltas is not None
    assert deltas["hit@1"] == pytest.approx(0.1)
    assert deltas["hit@3"] == 0
    assert deltas["new"] is None


# --- answer scoring -----------------------------------------------------------------------


def source(filename: str, heading: str) -> Source:
    location = Location("pdf", page=1, heading=heading)
    return Source(1, "doc", filename, location, "text", 0.7)


def test_missing_facts_ignores_case_markers_and_no_break_spaces():
    answer = "We open 9:00\N{NO-BREAK SPACE}AM [1] and close at 1:00 pm[2]."
    assert missing_facts(answer, [r"9(:00)?\s*am", r"1(:00)?\s*pm"]) == []
    assert missing_facts(answer, [r"\$40", "am"]) == [r"\$40"]


def test_cited_correctly_checks_file_and_section():
    assert cited_correctly([source(PDF, "1. Opening hours")], [HOURS]) == (True, True)
    assert cited_correctly([source(PDF, "3. Insurance")], [HOURS]) == (True, False)
    assert cited_correctly([], [HOURS]) == (False, False)


def done(answer: str, citations: list[Source], *, refused: bool = False) -> DoneEvent:
    return DoneEvent(answer, citations, refused, not refused and not citations, "q")


def question(kind: str = "answerable", **overrides: object) -> GoldenQuestion:
    return parse_questions({"question": [entry(kind=kind, **overrides)]})[0]


def test_a_correct_cited_answer_passes():
    score = score_answer(question(), done("From 9 am [1].", [source(PDF, HOURS.section)]), True)

    assert score.passed
    assert (score.cited_file_ok, score.cited_section_ok, score.uncited) == (True, True, False)


def test_an_answer_missing_a_fact_or_refused_fails():
    assert not score_answer(
        question(), done("Noon [1].", [source(PDF, HOURS.section)]), True
    ).passed
    refused = score_answer(question(), done(NOT_FOUND, [], refused=True), True)
    assert not refused.passed
    assert refused.refused_by == "llm"


def test_an_uncited_answer_is_flagged_and_fails():
    score = score_answer(question(), done("From 9 am.", []), True)

    assert score.uncited
    assert not score.passed


def test_unanswerable_passes_when_refused_and_records_who_refused():
    unanswerable = question("unanswerable", facts=[], sources=[], topic="off")

    by_threshold = score_answer(unanswerable, done(NOT_FOUND, [], refused=True), False)
    by_llm = score_answer(unanswerable, done(NOT_FOUND, [], refused=True), True)
    answered = score_answer(unanswerable, done("Sunny [1].", [source(PDF, "x")]), True)

    assert (by_threshold.passed, by_threshold.refused_by) == (True, "threshold")
    assert (by_llm.passed, by_llm.refused_by) == (True, "llm")
    assert not answered.passed


# --- results files ------------------------------------------------------------------------


def test_results_are_saved_per_run_and_the_previous_run_is_found(tmp_path: Path):
    assert load_previous(tmp_path, "retrieval") is None

    first = save_results(
        tmp_path, "retrieval", {"summary": {"a": 1}}, datetime(2026, 1, 1, tzinfo=UTC)
    )
    save_results(tmp_path, "answers", {"summary": {"b": 2}}, datetime(2026, 1, 3, tzinfo=UTC))
    second = save_results(
        tmp_path, "retrieval", {"summary": {"a": 2}}, datetime(2026, 1, 2, tzinfo=UTC)
    )

    assert ":" not in first.name
    assert json.loads(first.read_text(encoding="utf-8"))["summary"] == {"a": 1}
    assert load_previous(tmp_path, "retrieval") == {"summary": {"a": 2}}
    assert load_previous(tmp_path, "retrieval", before=second) == {"summary": {"a": 1}}


# --- the answer runner, offline -------------------------------------------------------------


@pytest.fixture
def demo_store(api_store: ChromaVectorStore) -> ChromaVectorStore:
    index_demo_docs(api_store, count_tokens=lambda text: len(text.split()))
    return api_store


def rag(store: ChromaVectorStore, chat: FakeChat) -> RagService:
    return RagService(
        store,
        chat,
        count_tokens=lambda text: len(text.split()),
        top_k=3,
        min_score=0.0,
        token_budget=5000,
        history_tokens=500,
        max_output_tokens=100,
    )


def estimates(*reaches: bool) -> list[Estimate]:
    return [Estimate(llm_calls=int(r), prompt_tokens=0, worst_case_tokens=0) for r in reaches]


async def test_runner_waits_only_between_questions_that_call_the_llm(
    demo_store: ChromaVectorStore,
):
    by_id = {q.id: q for q in QUESTIONS}
    chosen = [by_id["hours-saturday"], by_id["weather"], by_id["parking"]]
    chat = FakeChat("We open 9:00 am to 1:00 pm on Saturday [1].")
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    rows = await run_questions(
        chosen, estimates(True, False, True), rag(demo_store, chat), delay=60, sleep=sleep
    )

    assert sleeps == [60]  # before parking only: weather's estimate says it skips the LLM
    assert [row["id"] for row in rows] == ["hours-saturday", "weather", "parking"]
    assert rows[0]["passed"] is True
    assert rows[0]["input_tokens"] == 10
    assert rows[2]["passed"] is False  # the fake answered the parking question
    assert DEMO_WORKSPACE_ID


async def test_runner_retries_a_rate_limit_once_then_records_the_error(
    demo_store: ChromaVectorStore,
):
    chosen = [next(q for q in QUESTIONS if q.id == "hours-saturday")]
    chat = FakeChat(error=LLMRateLimitError("slow down"))
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    rows = await run_questions(
        chosen, estimates(True), rag(demo_store, chat), delay=60, sleep=sleep
    )

    assert sleeps == [60]
    assert len(chat.calls) == 2
    assert rows[0]["passed"] is False
    assert rows[0]["error"] == "LLMRateLimitError"
