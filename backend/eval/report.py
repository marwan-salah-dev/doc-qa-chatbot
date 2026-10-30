"""Plain-text tables and number formatting for the eval summaries."""

from collections.abc import Sequence

from app.config import Settings


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    cells = [[str(h) for h in headers], *[[_cell(value) for value in row] for row in rows]]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    lines = ["  ".join(value.ljust(widths[i]) for i, value in enumerate(row)) for row in cells]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines)


def _cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def delta(value: float | None) -> str:
    return "" if value is None else f"{value:+.3f}"


def settings_snapshot(settings: Settings) -> dict[str, object]:
    """What a run measured with: providers, models and RAG settings. Never keys."""
    llm_model = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    embedding_model = (
        settings.local_embedding_model
        if settings.embedding_provider == "local"
        else settings.openai_embedding_model
    )
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": llm_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": embedding_model,
        "rag_top_k": settings.rag_top_k,
        "rag_min_score": settings.rag_min_score,
        "rag_token_budget": settings.rag_token_budget,
        "llm_max_output_tokens": settings.llm_max_output_tokens,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_tokens": settings.chunk_overlap_tokens,
    }
