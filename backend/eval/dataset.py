"""Load and validate the golden questions in `golden.toml`."""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from app.services.llm import ChatMessage

GOLDEN_PATH = Path(__file__).with_name("golden.toml")

Kind = Literal["answerable", "followup", "unanswerable"]
Style = Literal["literal", "paraphrased", "non-english"]
Topic = Literal["off", "in-domain"]

KINDS: tuple[Kind, ...] = ("answerable", "followup", "unanswerable")
STYLES: tuple[Style, ...] = ("literal", "paraphrased", "non-english")
TOPICS: tuple[Topic, ...] = ("off", "in-domain")
OTHER_LANGUAGES = ("ar", "es", "fr")


class DatasetError(ValueError):
    """The golden file is malformed; the message names the question."""


@dataclass(frozen=True, slots=True)
class ExpectedSource:
    """A section that holds the answer: the file name and the chunk's heading."""

    file: str
    section: str


@dataclass(frozen=True, slots=True)
class GoldenQuestion:
    id: str
    kind: Kind
    style: Style
    question: str
    language: str = "en"
    facts: tuple[str, ...] = ()
    sources: tuple[ExpectedSource, ...] = ()
    topic: Topic | None = None
    history: tuple[ChatMessage, ...] = ()
    standalone: str | None = None
    answer_eval: bool = False

    @property
    def retrieval_query(self) -> str:
        """What retrieval searches for: a follow-up's hand-written standalone question."""
        return self.standalone or self.question

    @property
    def calibrated(self) -> bool:
        """Used for RAG_MIN_SCORE: English only, since the default embedder is English-only."""
        return self.language == "en"


def load_questions(path: Path = GOLDEN_PATH) -> list[GoldenQuestion]:
    with path.open("rb") as file:
        return parse_questions(tomllib.load(file))


def parse_questions(data: Mapping[str, Any]) -> list[GoldenQuestion]:
    questions = [_parse(entry) for entry in data.get("question", [])]
    seen: set[str] = set()
    for question in questions:
        if question.id in seen:
            raise DatasetError(f"duplicate question id {question.id!r}")
        seen.add(question.id)
    return questions


def _parse(entry: Mapping[str, Any]) -> GoldenQuestion:
    qid = str(entry.get("id", "?"))

    def fail(problem: str) -> DatasetError:
        return DatasetError(f"question {qid!r}: {problem}")

    kind, style = entry.get("kind"), entry.get("style")
    if kind not in KINDS:
        raise fail(f"kind must be one of {KINDS}")
    if style not in STYLES:
        raise fail(f"style must be one of {STYLES}")
    kind, style = cast(Kind, kind), cast(Style, style)

    facts = tuple(str(fact) for fact in entry.get("facts", []))
    for fact in facts:
        try:
            re.compile(fact)
        except re.error as exc:
            raise fail(f"fact {fact!r} is not a valid regex: {exc}") from exc
    sources = tuple(
        ExpectedSource(str(s["file"]), str(s["section"])) for s in entry.get("sources", [])
    )
    history = tuple(
        ChatMessage(cast(Literal["user", "assistant"], m["role"]), str(m["content"]))
        for m in entry.get("history", [])
    )
    standalone = entry.get("standalone")
    topic = entry.get("topic")
    language = str(entry.get("language", "en"))
    answer_eval = bool(entry.get("answer_eval", False))

    if kind == "unanswerable":
        if facts or sources:
            raise fail("unanswerable questions have no facts or sources")
        if topic not in TOPICS:
            raise fail(f"unanswerable questions need a topic in {TOPICS}")
    elif not facts or not sources:
        raise fail("needs facts and sources")
    if kind == "followup" and (not history or not standalone):
        raise fail("follow-ups need a history and a standalone question")
    if style == "non-english":
        if language not in OTHER_LANGUAGES:
            raise fail(f"non-english questions need a language in {OTHER_LANGUAGES}")
        if answer_eval:
            raise fail("non-english questions are retrieval-only")
    elif language != "en":
        raise fail("a question in another language must have style non-english")

    return GoldenQuestion(
        id=qid,
        kind=kind,
        style=style,
        question=str(entry["question"]),
        language=language,
        facts=facts,
        sources=sources,
        topic=cast(Topic | None, topic),
        history=history,
        standalone=str(standalone) if standalone else None,
        answer_eval=answer_eval,
    )
