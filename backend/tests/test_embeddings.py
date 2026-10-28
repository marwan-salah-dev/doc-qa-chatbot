import math
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.services.chunking import chunk_segments, estimate_tokens
from app.services.embeddings import (
    BGE_QUERY_PREFIX,
    LOCAL_MODEL_MAX_TOKENS,
    Embedder,
    FakeEmbedder,
    LocalEmbedder,
    OpenAIEmbedder,
    create_embedder,
    ensure_chunk_fits,
    model_slug,
)
from app.services.parsers import Location, Segment


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


# --- chunk size vs. the local model's input limit -------------------------------------------


def test_default_chunk_size_fits_local_model_limit():
    settings = make_settings()
    assert settings.local_embedding_model == "BAAI/bge-small-en-v1.5"
    assert LOCAL_MODEL_MAX_TOKENS == 512
    assert settings.chunk_size_tokens < LOCAL_MODEL_MAX_TOKENS


def test_chunks_are_sized_by_the_embedders_own_counter():
    # A model whose tokenizer is harsh on digits and punctuation: 1 token per character.
    class CharCounter(FakeEmbedder):
        def count_tokens(self, text: str) -> int:
            return len(text)

    embedder = CharCounter()
    hard = " ".join(f"SKU-{i:05d}/ref#{i * 7}" for i in range(500))
    segments = [Segment(hard, Location(kind="txt", start=1, end=1))]
    settings = make_settings()
    chunks = chunk_segments(
        segments,
        settings.chunk_size_tokens,
        settings.chunk_overlap_tokens,
        count_tokens=embedder.count_tokens,
    )
    assert len(chunks) > 1
    assert all(len(c.text) <= settings.chunk_size_tokens for c in chunks)


def test_ensure_chunk_fits_accepts_sizes_within_the_embedder_limit():
    ensure_chunk_fits(FakeEmbedder(), 350)
    ensure_chunk_fits(FakeEmbedder(), FakeEmbedder().max_tokens)


def test_ensure_chunk_fits_rejects_sizes_over_the_embedder_limit():
    with pytest.raises(ValueError, match="CHUNK_SIZE_TOKENS"):
        ensure_chunk_fits(FakeEmbedder(), FakeEmbedder().max_tokens + 1)


# --- token counting and limits on each embedder ---------------------------------------------


def test_fake_and_openai_embedders_use_the_estimator_and_report_their_limits():
    fake = FakeEmbedder()
    openai_embedder = OpenAIEmbedder("text-embedding-3-small", client=object())
    text = "Opening hours are 9 to 5."
    assert fake.count_tokens(text) == estimate_tokens(text)
    assert openai_embedder.count_tokens(text) == estimate_tokens(text)
    assert fake.max_tokens == 512
    assert openai_embedder.max_tokens == 8191


class StubTokenizer:
    """Stands in for tokenizers.Tokenizer: counts words, plus 2 for [CLS] and [SEP]."""

    def __init__(self) -> None:
        self.truncation_disabled = False
        self.padding_disabled = False

    def no_truncation(self) -> None:
        self.truncation_disabled = True

    def no_padding(self) -> None:
        self.padding_disabled = True

    def encode(self, text: str) -> Any:
        return SimpleNamespace(ids=list(range(len(text.split()) + 2)))


def test_local_embedder_counts_real_tokens_including_special_tokens():
    embedder = LocalEmbedder("BAAI/bge-small-en-v1.5", tokenizer_loader=lambda _: StubTokenizer())
    assert embedder.max_tokens == 512
    assert embedder.count_tokens("one two three") == 5
    assert embedder.count_tokens("") == 2


def test_local_embedder_loads_tokenizer_lazily_once_and_never_loads_the_model():
    loads: list[str] = []

    def tokenizer_loader(name: str) -> StubTokenizer:
        loads.append(name)
        return StubTokenizer()

    def model_loader(name: str) -> Any:
        raise AssertionError("counting tokens must not load the embedding model")

    embedder = LocalEmbedder(
        "BAAI/bge-small-en-v1.5", model_loader=model_loader, tokenizer_loader=tokenizer_loader
    )
    assert loads == []
    embedder.count_tokens("a b")
    embedder.count_tokens("c d")
    assert loads == ["BAAI/bge-small-en-v1.5"]


def test_local_embedder_turns_off_tokenizer_truncation_so_long_text_is_counted_in_full():
    tokenizer = StubTokenizer()
    LocalEmbedder("BAAI/bge-small-en-v1.5", tokenizer_loader=lambda _: tokenizer).count_tokens("x")
    assert tokenizer.truncation_disabled
    assert tokenizer.padding_disabled


# --- FakeEmbedder ---------------------------------------------------------------------------


def test_fake_embedder_is_deterministic_and_normalised():
    fake = FakeEmbedder()
    first = fake.embed_documents(["opening hours are nine to five"])[0]
    again = fake.embed_documents(["opening hours are nine to five"])[0]
    assert first == again
    assert len(first) == fake.dimension
    assert math.isclose(math.sqrt(sum(x * x for x in first)), 1.0, rel_tol=1e-9)


def test_fake_embedder_returns_one_vector_per_text():
    assert len(FakeEmbedder().embed_documents(["a", "b", "c"])) == 3
    assert FakeEmbedder().embed_documents([]) == []


def test_fake_embedder_ranks_overlapping_text_higher():
    fake = FakeEmbedder()
    query = fake.embed_query("refund policy for damaged items")
    related = fake.embed_documents(["our refund policy covers damaged items"])[0]
    unrelated = fake.embed_documents(["parking is available behind the building"])[0]
    assert cosine(query, related) > cosine(query, unrelated)


def test_fake_embedder_handles_empty_text():
    vector = FakeEmbedder().embed_query("")
    assert len(vector) == FakeEmbedder().dimension


# --- LocalEmbedder (sentence-transformers is replaced by a stub) ----------------------------


class StubSentenceModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.calls.append(texts)
        self.kwargs = kwargs
        return [[float(len(t)), 0.0] for t in texts]


def test_local_embedder_loads_model_lazily_and_only_once():
    loads: list[str] = []
    stub = StubSentenceModel()

    def loader(name: str) -> StubSentenceModel:
        loads.append(name)
        return stub

    embedder = LocalEmbedder("BAAI/bge-small-en-v1.5", model_loader=loader)
    assert loads == []
    embedder.embed_documents(["a"])
    embedder.embed_query("b")
    assert loads == ["BAAI/bge-small-en-v1.5"]


def test_local_embedder_prefixes_queries_but_not_documents_for_bge():
    stub = StubSentenceModel()
    embedder = LocalEmbedder("BAAI/bge-small-en-v1.5", model_loader=lambda _: stub)
    embedder.embed_documents(["the passage"])
    embedder.embed_query("the question")
    assert stub.calls[0] == ["the passage"]
    assert stub.calls[1] == [BGE_QUERY_PREFIX + "the question"]


def test_local_embedder_does_not_prefix_other_models():
    stub = StubSentenceModel()
    embedder = LocalEmbedder("sentence-transformers/all-MiniLM-L6-v2", model_loader=lambda _: stub)
    embedder.embed_query("the question")
    assert stub.calls == [["the question"]]


def test_local_embedder_asks_for_normalised_vectors_and_returns_plain_lists():
    stub = StubSentenceModel()
    embedder = LocalEmbedder("BAAI/bge-small-en-v1.5", model_loader=lambda _: stub)
    vectors = embedder.embed_documents(["abc"])
    assert stub.kwargs["normalize_embeddings"] is True
    assert vectors == [[3.0, 0.0]]
    assert embedder.embed_documents([]) == []


# --- OpenAIEmbedder (the SDK client is replaced by a stub) ----------------------------------


class StubOpenAIClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, *, model: str, input: list[str]) -> Any:
        self.requests.append({"model": model, "input": input})
        # Return out of order to prove the embedder sorts by index.
        items = [SimpleNamespace(index=i, embedding=[float(i), 1.0]) for i in range(len(input))]
        return SimpleNamespace(data=list(reversed(items)))


def test_openai_embedder_sends_model_and_keeps_input_order():
    client = StubOpenAIClient()
    embedder = OpenAIEmbedder("text-embedding-3-small", client=client)
    vectors = embedder.embed_documents(["a", "b", "c"])
    assert client.requests == [{"model": "text-embedding-3-small", "input": ["a", "b", "c"]}]
    assert vectors == [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]


def test_openai_embedder_batches_large_inputs():
    client = StubOpenAIClient()
    embedder = OpenAIEmbedder("text-embedding-3-small", client=client, batch_size=2)
    vectors = embedder.embed_documents(["a", "b", "c", "d", "e"])
    assert [len(r["input"]) for r in client.requests] == [2, 2, 1]
    assert len(vectors) == 5


def test_openai_embedder_query_has_no_prefix():
    client = StubOpenAIClient()
    OpenAIEmbedder("text-embedding-3-small", client=client).embed_query("question")
    assert client.requests[0]["input"] == ["question"]


def test_openai_embedder_skips_the_api_for_no_texts():
    client = StubOpenAIClient()
    assert OpenAIEmbedder("text-embedding-3-small", client=client).embed_documents([]) == []
    assert client.requests == []


# --- factory and slugs ----------------------------------------------------------------------


def test_factory_builds_local_embedder_by_default():
    embedder = create_embedder(make_settings())
    assert isinstance(embedder, LocalEmbedder)
    assert embedder.model_name == "BAAI/bge-small-en-v1.5"


def test_factory_builds_openai_embedder_with_a_key():
    embedder = create_embedder(
        make_settings(embedding_provider="openai", openai_api_key="test-key")
    )
    assert isinstance(embedder, OpenAIEmbedder)
    assert embedder.model_name == "text-embedding-3-small"


def test_factory_requires_a_key_for_openai():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_embedder(make_settings(embedding_provider="openai", openai_api_key=""))


def test_every_embedder_satisfies_the_protocol():
    embedders: list[Embedder] = [
        FakeEmbedder(),
        LocalEmbedder("BAAI/bge-small-en-v1.5"),
        OpenAIEmbedder("text-embedding-3-small", client=StubOpenAIClient()),
    ]
    assert all(e.slug for e in embedders)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("BAAI/bge-small-en-v1.5", "bge-small-en-v1-5"),
        ("sentence-transformers/all-MiniLM-L6-v2", "all-minilm-l6-v2"),
        ("text-embedding-3-small", "text-embedding-3-small"),
    ],
)
def test_model_slug_is_safe_for_collection_names(name: str, slug: str):
    assert model_slug(name) == slug
