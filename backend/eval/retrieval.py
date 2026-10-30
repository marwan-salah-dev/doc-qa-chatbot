"""Retrieval eval: hit@k and score distributions, with no LLM calls (free).

Indexes the demo files in memory with the configured embedder and asks every golden question.
Recommends a RAG_MIN_SCORE from English answerable vs off-topic top scores.

    uv run python -m eval.retrieval [--k 1,3,6]
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Any

from app.config import Settings
from eval.dataset import GoldenQuestion, load_questions
from eval.index import DEMO_WORKSPACE_ID, build_demo_store
from eval.report import delta, percent, settings_snapshot, table
from eval.results import RESULTS_DIR, git_commit, load_previous, save_results
from eval.scoring import (
    best_expected_score,
    compare_with_previous,
    first_hit_rank,
    hit_rate,
    recommend_threshold,
    score_distribution,
)

MULTILINGUAL_NOTE = (
    "Fixing non-English retrieval: EMBEDDING_PROVIDER=openai (text-embedding-3-small) is already "
    "supported and multilingual, with no RAM cost but a per-call price. Locally, "
    "intfloat/multilingual-e5-small (MIT, 118M params, ~0.47 GB of fp32 weights vs bge-small's "
    "~0.13 GB) would lift the backend's measured 600-780 MB peak to roughly 1.0-1.1 GB, tight "
    "against the 1200 MB container limit, so it must be measured; BAAI/bge-m3 (MIT, 568M params, "
    "~2.3 GB) does not fit a 2 GB VPS. e5 needs 'query: '/'passage: ' prefixes (LocalEmbedder "
    "only knows bge's), every workspace must be re-indexed (new collection slug), RAG_MIN_SCORE "
    "re-calibrated, and the threshold refusal (NOT_FOUND) is English-only today."
)

Row = dict[str, Any]


def evaluate(question: GoldenQuestion, store: Any, k: int, min_score: float) -> Row:
    hits = store.query(DEMO_WORKSPACE_ID, question.retrieval_query, k)
    top = hits[0] if hits else None
    row: Row = {
        "id": question.id,
        "kind": question.kind,
        "style": question.style,
        "language": question.language,
        "topic": question.topic,
        "top_score": round(top.score, 4) if top else None,
        "top_hit": f"{top.chunk.filename} · {top.chunk.location.label()}" if top else None,
        "rank": None,
        "rank_above_threshold": None,
        "best_expected_score": None,
    }
    if question.sources:
        row["rank"] = first_hit_rank(hits, question.sources)
        row["rank_above_threshold"] = first_hit_rank(hits, question.sources, min_score)
        best = best_expected_score(hits, question.sources)
        row["best_expected_score"] = None if best is None else round(best, 4)
    if question.kind == "followup":
        raw = store.query(DEMO_WORKSPACE_ID, question.question, k)
        row["raw_rank"] = first_hit_rank(raw, question.sources)
        row["raw_top_score"] = round(raw[0].score, 4) if raw else None
    return row


def group_of(row: Row) -> str:
    if row["style"] == "non-english":
        return f"answerable, {row['language']}"
    if row["kind"] == "unanswerable":
        return f"unanswerable, {row['topic']}"
    if row["kind"] == "followup":
        return "follow-up (standalone)"
    return f"answerable, {row['style']}"


HIT_GROUPS: list[tuple[str, Callable[[Row], bool], str]] = [
    ("answerable, literal", lambda r: group_of(r) == "answerable, literal", "rank"),
    ("answerable, paraphrased", lambda r: group_of(r) == "answerable, paraphrased", "rank"),
    ("follow-up (standalone)", lambda r: r["kind"] == "followup", "rank"),
    ("follow-up (raw question)", lambda r: r["kind"] == "followup", "raw_rank"),
    (
        "all English answerable",
        lambda r: r["kind"] != "unanswerable" and r["language"] == "en",
        "rank",
    ),
    ("answerable, ar", lambda r: group_of(r) == "answerable, ar", "rank"),
    ("answerable, es", lambda r: group_of(r) == "answerable, es", "rank"),
    ("answerable, fr", lambda r: group_of(r) == "answerable, fr", "rank"),
]


def summarize(rows: Sequence[Row], ks: Sequence[int], min_score: float) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, keep, rank_key in HIT_GROUPS:
        chosen = [r for r in rows if keep(r)]
        for k in ks:
            summary[f"{name} hit@{k}"] = hit_rate([r[rank_key] for r in chosen], k)
        if rank_key == "rank":
            summary[f"{name} hit@{max(ks)} above threshold"] = hit_rate(
                [r["rank_above_threshold"] for r in chosen], max(ks)
            )

    calibrated = [
        r["top_score"] for r in rows if r["kind"] != "unanswerable" and r["language"] == "en"
    ]
    off_topic = [r["top_score"] for r in rows if r["topic"] == "off"]
    rec = recommend_threshold(calibrated, off_topic)
    summary.update(
        recommended_threshold=rec.threshold,
        lowest_answerable=rec.lowest_answerable,
        highest_off_topic=rec.highest_off_topic,
        margin_below_answerable=round(rec.margin_below_answerable, 4),
        margin_above_off_topic=round(rec.margin_above_off_topic, 4),
        overlap=rec.overlap,
        current_threshold=min_score,
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--k", default="", help="comma-separated k values (default 1,3,RAG_TOP_K)")
    args = parser.parse_args(argv)

    settings = Settings(public_demo=False)
    ks = sorted({int(k) for k in args.k.split(",")} if args.k else {1, 3, settings.rag_top_k})
    min_score = settings.rag_min_score
    questions = load_questions()

    print("Indexing the demo files...")
    _, store, chunks = build_demo_store(settings)
    snapshot = settings_snapshot(settings)
    print(
        f"{chunks} chunks, embedder {snapshot['embedding_provider']} / "
        f"{snapshot['embedding_model']}, RAG_MIN_SCORE={min_score}, {len(questions)} questions\n"
    )
    rows = [evaluate(q, store, max(ks), min_score) for q in questions]
    summary = summarize(rows, ks, min_score)
    previous = load_previous(RESULTS_DIR, "retrieval")
    deltas = compare_with_previous(
        {k: v for k, v in summary.items() if isinstance(v, float) and not isinstance(v, bool)},
        previous["summary"] if previous else None,
    )

    def with_delta(key: str) -> str:
        value = percent(summary[key])
        change = deltas.get(key) if deltas else None
        return f"{value} ({change:+.0%})" if change else value

    print("Hit rate: the expected section is in the top k")
    hit_rows = []
    for name, keep, _rank_key in HIT_GROUPS:
        n = sum(1 for r in rows if keep(r))
        above = summary.get(f"{name} hit@{max(ks)} above threshold", "n/a")
        hit_rows.append(
            [
                name,
                n,
                *[with_delta(f"{name} hit@{k}") for k in ks],
                percent(above) if isinstance(above, float) else "-",
            ]
        )
    print(
        table(["group", "n", *[f"hit@{k}" for k in ks], f"hit@{max(ks)} >= {min_score}"], hit_rows)
    )

    print("\nTop-1 score by group")
    groups = sorted({group_of(r) for r in rows})
    dist_rows = []
    for name in groups:
        dist = score_distribution([r["top_score"] for r in rows if group_of(r) == name])
        if dist:
            dist_rows.append([name, dist.count, dist.min, dist.median, dist.max])
    print(table(["group", "n", "min", "median", "max"], dist_rows))

    print(f"\nEvery question by top-1 score ('|' marks RAG_MIN_SCORE={min_score})")
    marked = False
    for row in sorted(rows, key=lambda r: r["top_score"] or 0, reverse=True):
        if not marked and (row["top_score"] or 0) < min_score:
            print(f"  ------ {min_score:.2f} | below: refused without calling the LLM ------")
            marked = True
        rank = (
            "" if row["kind"] == "unanswerable" else f"  (expected at rank {row['rank'] or 'miss'})"
        )
        print(f"  {row['top_score']:.3f}  {group_of(row):<26} {row['id']}{rank}")

    rec = summary
    print("\nRecommendation (English answerable incl. follow-ups vs off-topic; in-domain and")
    print("non-English questions are excluded: the LLM refuses the former, the latter is a gap)")
    print(
        f"  lowest answerable top score {rec['lowest_answerable']:.3f}, highest off-topic "
        f"{rec['highest_off_topic']:.3f}" + ("  ** OVERLAP **" if rec["overlap"] else "")
    )
    print(
        f"  RAG_MIN_SCORE={rec['recommended_threshold']:.2f}: margin "
        f"{rec['margin_below_answerable']:+.3f} below the lowest answerable, "
        f"{rec['margin_above_off_topic']:+.3f} above the highest off-topic"
    )
    for label, threshold in (("current", min_score), ("recommended", rec["recommended_threshold"])):
        refused = [
            r["id"]
            for r in rows
            if r["kind"] != "unanswerable" and r["language"] == "en" and r["top_score"] < threshold
        ]
        through = [r["id"] for r in rows if r["topic"] == "off" and r["top_score"] >= threshold]
        in_domain = [
            r["id"] for r in rows if r["topic"] == "in-domain" and r["top_score"] >= threshold
        ]
        foreign = [
            r["id"] for r in rows if r["style"] == "non-english" and r["top_score"] < threshold
        ]
        print(
            f"  at {label} {threshold:.2f}: answerable refused {refused or 'none'}; "
            f"off-topic reaching the LLM {through or 'none'}; "
            f"in-domain reaching the LLM {len(in_domain)}/"
            f"{sum(1 for r in rows if r['topic'] == 'in-domain')}; non-English refused "
            f"{len(foreign)}/{sum(1 for r in rows if r['style'] == 'non-english')}"
        )
    if deltas:
        for key in ("recommended_threshold", "lowest_answerable", "highest_off_topic"):
            print(f"  {key} vs previous run: {delta(deltas.get(key)) or '0'}")
    print(f"\n{MULTILINGUAL_NOTE}")

    path = save_results(
        RESULTS_DIR,
        "retrieval",
        {
            "commit": git_commit(),
            "settings": snapshot,
            "chunks": chunks,
            "summary": summary,
            "multilingual_note": MULTILINGUAL_NOTE,
            "rows": rows,
        },
    )
    print(f"\nSaved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
