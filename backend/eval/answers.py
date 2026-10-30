"""Answer eval: the `answer_eval` subset through the real RagService and LLM.

Without `--run` it only prints the token estimate (retrieval is local and free). With `--run`
it asks each question in-process (no server, so PUBLIC_DEMO's caps and limits don't apply),
waiting `--delay` seconds between LLM calls for Groq's free 8K tokens per minute.

    uv run python -m eval.answers
    uv run python -m eval.answers --run [--delay 60] [--only hours-saturday,parking]
"""

import argparse
import asyncio
import math
import sys
from collections.abc import Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.chunking import TokenCounter
from app.services.llm import LLMError, LLMRateLimitError, Usage, create_chat_model
from app.services.rag import (
    CONDENSE_MAX_TOKENS,
    CONDENSE_PROMPT,
    SYSTEM_PROMPT,
    DoneEvent,
    RagService,
    SourcesEvent,
    build_condense_prompt,
    build_messages,
    fit_budget,
    trim_history,
)
from app.services.vectorstore import VectorStore
from eval.dataset import GoldenQuestion, load_questions
from eval.index import DEMO_WORKSPACE_ID, build_demo_store
from eval.report import delta, percent, settings_snapshot, table
from eval.results import RESULTS_DIR, git_commit, load_previous, save_results
from eval.scoring import compare_with_previous, score_answer

# The bge tokenizer is not the LLM's; pad its count so the estimate errs high
TOKENIZER_MARGIN = 1.2
# A run whose worst case passes this is refused (Groq free: 200K tokens per day)
MAX_RUN_TOKENS = 50_000
# Groq free: about 8K tokens per minute; no single call may come near it
MAX_CALL_TOKENS = 8_000

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Estimate:
    """LLM calls one question will make, its prompt tokens, and the worst case with output."""

    llm_calls: int
    prompt_tokens: int
    worst_case_tokens: int
    largest_call: int = 0


def estimate_question(
    question: GoldenQuestion, store: VectorStore, settings: Settings, count_tokens: TokenCounter
) -> Estimate:
    """Replays RagService's budgeting with the real retrieval, counting tokens instead of calling.

    Follow-ups retrieve with the hand-written standalone question, which stands in for the
    model's own rewrite.
    """
    calls: list[tuple[int, int]] = []  # (prompt tokens, worst case) per call
    history = trim_history(question.history, settings.rag_history_tokens, count_tokens)
    if history:
        prompt = count_tokens(CONDENSE_PROMPT) + count_tokens(
            build_condense_prompt(question.question, history)
        )
        calls.append((prompt, math.ceil(prompt * TOKENIZER_MARGIN) + CONDENSE_MAX_TOKENS))

    found = store.query(DEMO_WORKSPACE_ID, question.retrieval_query, settings.rag_top_k)
    hits = [hit for hit in found if hit.score >= settings.rag_min_score]
    if hits:
        kept, sources = fit_budget(
            history,
            hits,
            question.question,
            system=SYSTEM_PROMPT,
            budget=settings.rag_token_budget - settings.llm_max_output_tokens,
            count_tokens=count_tokens,
        )
        messages = build_messages(kept, sources, question.question)
        prompt = count_tokens(SYSTEM_PROMPT) + sum(count_tokens(m.content) for m in messages)
        calls.append(
            (prompt, math.ceil(prompt * TOKENIZER_MARGIN) + settings.llm_max_output_tokens)
        )
    return Estimate(
        llm_calls=len(calls),
        prompt_tokens=sum(prompt for prompt, _ in calls),
        worst_case_tokens=sum(worst for _, worst in calls),
        largest_call=max((worst for _, worst in calls), default=0),
    )


async def run_questions(
    questions: Sequence[GoldenQuestion],
    estimates: Sequence[Estimate],
    rag: RagService,
    *,
    delay: float,
    sleep: Sleep = asyncio.sleep,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Ask each question and score it. Waits `delay` before a question that will call the LLM
    once any LLM call has been made; one refused by the threshold costs nothing, so no wait."""
    rows: list[dict[str, Any]] = []
    called = False
    for question, estimate in zip(questions, estimates, strict=True):
        if estimate.llm_calls and called:
            log(f"  waiting {delay:.0f} s (Groq tokens per minute)")
            await sleep(delay)
        log(f"  asking {question.id}")
        row = await _ask(question, rag, delay=delay, sleep=sleep, log=log)
        called = called or estimate.llm_calls > 0 or row["input_tokens"] > 0
        rows.append(row)
    return rows


async def _ask(
    question: GoldenQuestion,
    rag: RagService,
    *,
    delay: float,
    sleep: Sleep,
    log: Callable[[str], None],
) -> dict[str, Any]:
    usages: list[Usage] = []
    row: dict[str, Any] = {"id": question.id, "kind": question.kind, "question": question.question}
    for attempt in (1, 2):
        try:
            done, reached_llm = await _answer(question, rag, usages)
        except LLMRateLimitError:
            if attempt == 1:
                log(f"  rate limited; waiting {delay:.0f} s and retrying once")
                await sleep(delay)
                continue
            row.update(_failed("LLMRateLimitError", usages))
            return row
        except LLMError as exc:
            row.update(_failed(type(exc).__name__, usages))
            return row
        score = score_answer(question, done, reached_llm)
        row.update(
            answer=done.answer,
            standalone_question=done.standalone_question,
            citations=[f"{c.filename} · {c.location.label()}" for c in done.citations],
            passed=score.passed,
            refused=score.refused,
            refused_by=score.refused_by,
            missing_facts=score.missing_facts,
            cited_file_ok=score.cited_file_ok,
            cited_section_ok=score.cited_section_ok,
            uncited=score.uncited,
            error=None,
            **_tokens(usages),
        )
        return row
    raise AssertionError("unreachable")


async def _answer(
    question: GoldenQuestion, rag: RagService, usages: list[Usage]
) -> tuple[DoneEvent, bool]:
    reached_llm = False
    events = rag.answer(
        DEMO_WORKSPACE_ID, question.question, question.history, on_usage=usages.append
    )
    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, SourcesEvent):
                reached_llm = bool(event.sources)
            elif isinstance(event, DoneEvent):
                return event, reached_llm
    raise RuntimeError("the answer stream ended without a done event")


def _tokens(usages: Sequence[Usage]) -> dict[str, int]:
    return {
        "input_tokens": sum(u.input_tokens or 0 for u in usages),
        "output_tokens": sum(u.output_tokens or 0 for u in usages),
    }


def _failed(error: str, usages: Sequence[Usage]) -> dict[str, Any]:
    return {
        "passed": False,
        "refused": False,
        "refused_by": None,
        "error": error,
        **_tokens(usages),
    }


def summarize(
    questions: Sequence[GoldenQuestion], rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    by_id = {q.id: q for q in questions}
    answerable = [r for r in rows if by_id[r["id"]].kind != "unanswerable"]
    unanswerable = [r for r in rows if by_id[r["id"]].kind == "unanswerable"]

    def share(items: Sequence[dict[str, Any]], key: str) -> float | None:
        return sum(1 for r in items if r.get(key)) / len(items) if items else None

    return {
        "passed": share(rows, "passed"),
        "answer_accuracy": share(answerable, "passed"),
        "facts_ok": (
            sum(
                1
                for r in answerable
                if not r.get("refused") and not r.get("missing_facts") and not r.get("error")
            )
            / len(answerable)
            if answerable
            else None
        ),
        "citation_file_accuracy": share(answerable, "cited_file_ok"),
        "citation_section_accuracy": share(answerable, "cited_section_ok"),
        "refusal_accuracy": share(unanswerable, "refused"),
        "uncited": sum(1 for r in rows if r.get("uncited")),
        "errors": sum(1 for r in rows if r.get("error")),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
    }


def _yes_no(value: object) -> str:
    return "y" if value else "n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--run", action="store_true", help="make the real LLM calls")
    parser.add_argument("--delay", type=float, default=60, help="seconds between LLM calls")
    parser.add_argument("--only", default="", help="comma-separated question ids")
    args = parser.parse_args(argv)

    settings = Settings(public_demo=False)
    questions = [q for q in load_questions() if q.answer_eval]
    if args.only:
        wanted = {qid.strip() for qid in args.only.split(",")}
        questions = [q for q in questions if q.id in wanted]
    if not questions:
        print("No questions selected.")
        return 1

    print("Indexing the demo files...")
    embedder, store, _ = build_demo_store(settings)
    estimates = [estimate_question(q, store, settings, embedder.count_tokens) for q in questions]
    snapshot = settings_snapshot(settings)
    print(
        f"\nLLM: {snapshot['llm_provider']} / {snapshot['llm_model']}, "
        f"RAG_MIN_SCORE={settings.rag_min_score}\n"
    )
    print(
        table(
            ["question", "LLM calls", "prompt tokens", "worst case"],
            [
                [q.id, e.llm_calls, e.prompt_tokens, e.worst_case_tokens]
                for q, e in zip(questions, estimates, strict=True)
            ],
        )
    )
    total = sum(e.worst_case_tokens for e in estimates)
    largest = max(e.largest_call for e in estimates)
    calls = sum(e.llm_calls for e in estimates)
    waits = sum(1 for e in estimates if e.llm_calls) - 1
    print(
        f"\nEstimate: {sum(e.prompt_tokens for e in estimates)} prompt tokens, worst case {total} "
        f"in {calls} LLM calls ({total / 200_000:.0%} of Groq's free 200K/day). Largest single "
        f"call {largest} (limit ~{MAX_CALL_TOKENS}/min). "
        f"About {max(waits, 0) * args.delay / 60:.0f} min with waits."
    )
    if total > MAX_RUN_TOKENS or largest > MAX_CALL_TOKENS:
        print(f"Refusing to run: over {MAX_RUN_TOKENS} tokens or {MAX_CALL_TOKENS} in one call.")
        return 1
    if not args.run:
        print("\nDry run: no LLM calls made. Add --run to ask the questions.")
        return 0

    chat = create_chat_model(settings)
    rag = RagService(
        store,
        chat,
        count_tokens=embedder.count_tokens,
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        token_budget=settings.rag_token_budget,
        history_tokens=settings.rag_history_tokens,
        max_output_tokens=settings.llm_max_output_tokens,
    )

    async def go() -> list[dict[str, Any]]:
        try:
            return await run_questions(questions, estimates, rag, delay=args.delay)
        finally:
            await chat.aclose()

    print()
    rows = asyncio.run(go())
    summary = summarize(questions, rows)
    previous = load_previous(RESULTS_DIR, "answers")
    deltas = compare_with_previous(
        {k: v for k, v in summary.items() if isinstance(v, float)},
        previous["summary"] if previous else None,
    )

    print()
    print(
        table(
            ["question", "result", "refused by", "missing facts", "cited (file/section)", "tokens"],
            [
                [
                    r["id"],
                    "PASS"
                    if r["passed"]
                    else ("ERROR " + r["error"] if r.get("error") else "FAIL"),
                    r.get("refused_by"),
                    ", ".join(r.get("missing_facts") or []) or None,
                    _yes_no(r.get("cited_file_ok")) + "/" + _yes_no(r.get("cited_section_ok")),
                    r["input_tokens"] + r["output_tokens"],
                ]
                for r in rows
            ],
        )
    )
    print()
    metrics = [
        "answer_accuracy",
        "facts_ok",
        "citation_file_accuracy",
        "citation_section_accuracy",
        "refusal_accuracy",
    ]
    print(
        table(
            ["metric", "value", "vs previous"],
            [[m, percent(summary[m]), delta(deltas.get(m)) if deltas else ""] for m in metrics],
        )
    )
    used = summary["input_tokens"] + summary["output_tokens"]
    print(
        f"\nUncited answers: {summary['uncited']}. Errors: {summary['errors']}. Tokens used: "
        f"{used} ({summary['input_tokens']} in, {summary['output_tokens']} out) against a worst "
        f"case estimate of {total}."
    )
    path = save_results(
        RESULTS_DIR,
        "answers",
        {
            "commit": git_commit(),
            "settings": snapshot,
            "estimate": {"worst_case_tokens": total, "llm_calls": calls},
            "summary": summary,
            "rows": rows,
        },
    )
    print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
