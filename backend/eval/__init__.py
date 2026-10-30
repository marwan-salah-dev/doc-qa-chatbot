"""Quality evals over the demo documents: retrieval (free) and answers (real LLM, small subset).

Run from backend/:

    uv run python -m eval.retrieval
    uv run python -m eval.answers          # token estimate only
    uv run python -m eval.answers --run    # real LLM calls, spaced for Groq's free tier
"""
