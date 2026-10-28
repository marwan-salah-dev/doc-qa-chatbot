"""Checks against the real bge-small model. Skipped by default; run with `uv run pytest -m slow`.

The first run downloads the model (about 130 MB) from Hugging Face.
"""

import pytest

from app.config import Settings
from app.services.chunking import chunk_segments
from app.services.embeddings import LocalEmbedder
from app.services.parsers import Location, Segment

pytestmark = pytest.mark.slow

MODEL = "BAAI/bge-small-en-v1.5"


def test_default_chunks_fit_the_real_tokenizer_and_embed_to_384_dims():
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    embedder = LocalEmbedder(MODEL)
    assert embedder.max_tokens == 512

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL)
    assert model.max_seq_length == 512

    hard = " ".join(f"SKU-{i:05d}/ref#{i * 7}" for i in range(2000))
    segments = [Segment(hard, Location(kind="txt", start=1, end=1))]
    chunks = chunk_segments(
        segments,
        settings.chunk_size_tokens,
        settings.chunk_overlap_tokens,
        count_tokens=embedder.count_tokens,
    )
    assert chunks

    # Measure with sentence-transformers' own tokenizer, independent of the embedder's counter.
    # Its counts include the [CLS] and [SEP] the model adds, exactly as embedding does.
    counts = [len(model.tokenizer(c.text)["input_ids"]) for c in chunks]
    assert max(counts) <= 512, f"longest chunk is {max(counts)} real tokens"
    assert max(counts) <= settings.chunk_size_tokens
    assert counts == [embedder.count_tokens(c.text) for c in chunks]

    query = embedder.embed_query("What is the refund policy?")
    document = embedder.embed_documents(["Refunds are issued within 14 days."])[0]
    assert len(query) == 384
    assert len(document) == 384
