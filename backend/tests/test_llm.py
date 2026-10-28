import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import anthropic
import anyio
import httpx2
import openai
import pytest

from app.api.deps import get_chat_model
from app.config import Settings
from app.services.llm import (
    AnthropicChat,
    ChatMessage,
    ChatModel,
    FakeChat,
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    OpenAIChat,
    Usage,
    create_chat_model,
)

pytestmark = pytest.mark.anyio

FAKE_KEY = "sk-test-not-a-real-key-123"
QUESTION = [ChatMessage(role="user", content="What is the refund window?")]
REQUEST = httpx2.Request("POST", "https://api.example.test/v1/messages")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


async def collect(stream: Any) -> list[str]:
    return [delta async for delta in stream]


class UsageLog:
    """An `on_usage` callback that remembers what it was given."""

    def __init__(self) -> None:
        self.calls: list[Usage] = []

    def __call__(self, usage: Usage) -> None:
        self.calls.append(usage)


# --- SDK stubs: same shapes as the real SDK objects, no network --------------------------------


class StubStream:
    """An SDK stream: an async context manager you iterate, which records being closed."""

    def __init__(
        self,
        items: list[Any],
        open_error: Exception | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.items = items
        self.open_error = open_error
        self.fail_with = fail_with
        self.consumed = 0
        self.closed = False

    async def __aenter__(self) -> "StubStream":
        if self.open_error:
            raise self.open_error
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.closed = True

    async def __aiter__(self) -> Any:
        for item in self.items:
            await anyio.sleep(0)  # let concurrent streams interleave
            self.consumed += 1
            yield item
        if self.fail_with:
            raise self.fail_with


def anthropic_events(texts: list[str], input_tokens: int = 12, output_tokens: int = 7) -> list[Any]:
    return [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(
                usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=1)
            ),
        ),
        *[SimpleNamespace(type="text", text=text) for text in texts],
        SimpleNamespace(type="message_delta", usage=SimpleNamespace(output_tokens=output_tokens)),
        SimpleNamespace(type="message_stop"),
    ]


class StubAnthropicClient:
    def __init__(self, *streams: StubStream, error: Exception | None = None) -> None:
        self.messages = self
        self._streams = list(streams)
        self.opened: list[StubStream] = []
        self.error = error
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    def stream(self, **kwargs: Any) -> StubStream:
        self.requests.append(kwargs)
        stream = self._streams.pop(0)
        self.opened.append(stream)
        return stream

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text="Thirty "),
                SimpleNamespace(type="text", text="days."),
            ],
            usage=SimpleNamespace(input_tokens=20, output_tokens=4),
        )

    async def close(self) -> None:
        self.closed = True


def openai_chunks(texts: list[str | None], prompt: int = 11, completion: int = 6) -> list[Any]:
    chunks: list[Any] = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None)
        for text in texts
    ]
    # With include_usage, the last chunk carries the usage and no choices.
    chunks.append(
        SimpleNamespace(
            choices=[], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
        )
    )
    return chunks


class StubOpenAIClient:
    def __init__(self, *streams: StubStream, error: Exception | None = None) -> None:
        self.chat = SimpleNamespace(completions=self)
        self._streams = list(streams)
        self.opened: list[StubStream] = []
        self.error = error
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        if kwargs.get("stream"):
            stream = self._streams.pop(0)
            self.opened.append(stream)
            return stream
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Thirty days."))],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=4),
        )

    async def close(self) -> None:
        self.closed = True


# --- factory and configuration ----------------------------------------------------------------


def test_factory_builds_anthropic_by_default_with_the_configured_model():
    chat = create_chat_model(make_settings(anthropic_api_key=FAKE_KEY))
    assert isinstance(chat, AnthropicChat)
    assert chat.model_name == "claude-sonnet-5-5"


def test_factory_builds_openai_with_the_configured_model():
    chat = create_chat_model(
        make_settings(llm_provider="openai", openai_api_key=FAKE_KEY, openai_model="gpt-test")
    )
    assert isinstance(chat, OpenAIChat)
    assert chat.model_name == "gpt-test"


def test_openai_uses_the_normal_endpoint_when_no_base_url_is_set(
    monkeypatch: pytest.MonkeyPatch,
):
    # The SDK reads OPENAI_BASE_URL from the environment itself, so clear it for this test.
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    chat = create_chat_model(make_settings(llm_provider="openai", openai_api_key=FAKE_KEY))
    assert isinstance(chat, OpenAIChat)
    assert str(chat._client.base_url) == "https://api.openai.com/v1/"


def test_openai_base_url_points_the_client_at_a_compatible_provider():
    # e.g. Groq, which speaks the same Chat Completions API
    chat = create_chat_model(
        make_settings(
            llm_provider="openai",
            openai_api_key=FAKE_KEY,
            openai_base_url="https://api.groq.com/openai/v1",
        )
    )
    assert isinstance(chat, OpenAIChat)
    assert str(chat._client.base_url) == "https://api.groq.com/openai/v1/"


@pytest.mark.parametrize(
    ("provider", "env_var"), [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")]
)
def test_factory_names_the_missing_key(provider: str, env_var: str):
    with pytest.raises(LLMConfigError, match=env_var):
        create_chat_model(make_settings(llm_provider=provider))


def test_factory_does_not_need_the_other_providers_key():
    # Only the selected provider's key matters.
    create_chat_model(make_settings(llm_provider="anthropic", anthropic_api_key=FAKE_KEY))


def test_factory_requires_a_model_name():
    with pytest.raises(LLMConfigError, match="OPENAI_MODEL"):
        create_chat_model(
            make_settings(llm_provider="openai", openai_api_key=FAKE_KEY, openai_model="")
        )


def test_keys_never_show_up_in_settings_repr_or_errors():
    settings = make_settings(anthropic_api_key=FAKE_KEY, openai_api_key=FAKE_KEY)
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings.model_dump())
    with pytest.raises(LLMConfigError) as excinfo:
        create_chat_model(
            make_settings(llm_provider="openai", openai_api_key=FAKE_KEY, openai_model="")
        )
    assert FAKE_KEY not in str(excinfo.value)


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_sdk_clients_get_our_timeout_and_retries(provider: str):
    chat = create_chat_model(
        make_settings(
            llm_provider=provider,
            anthropic_api_key=FAKE_KEY,
            openai_api_key=FAKE_KEY,
            llm_timeout_seconds=42,
            llm_max_retries=5,
        )
    )
    client: Any = chat._client  # pyright: ignore[reportAttributeAccessIssue]
    assert client.max_retries == 5
    assert client.timeout.read == 42
    assert client.timeout.connect == 10


# --- Anthropic --------------------------------------------------------------------------------


async def test_anthropic_streams_text_deltas_and_skips_empty_ones():
    client = StubAnthropicClient(StubStream(anthropic_events(["Refunds ", "", "take 30 days."])))
    chat = AnthropicChat("claude-sonnet-5-5", client=client, max_output_tokens=500, effort="low")

    deltas = await collect(chat.stream(QUESTION, system="Answer from the documents."))

    assert deltas == ["Refunds ", "take 30 days."]
    request = client.requests[0]
    assert request["model"] == "claude-sonnet-5-5"
    assert request["system"] == "Answer from the documents."
    assert request["messages"] == [{"role": "user", "content": "What is the refund window?"}]
    assert request["max_tokens"] == 500
    assert request["output_config"] == {"effort": "low"}
    assert "temperature" not in request


async def test_anthropic_leaves_out_an_empty_system_prompt_and_honours_max_tokens():
    client = StubAnthropicClient(StubStream(anthropic_events(["ok"])))
    chat = AnthropicChat("claude-sonnet-5-5", client=client)
    await collect(chat.stream(QUESTION, max_tokens=64))
    assert "system" not in client.requests[0]
    assert client.requests[0]["max_tokens"] == 64


async def test_anthropic_complete_joins_text_blocks_and_reports_usage():
    client = StubAnthropicClient()
    usage = UsageLog()
    text = await AnthropicChat("claude-sonnet-5-5", client=client).complete(
        QUESTION, on_usage=usage
    )
    assert text == "Thirty days."
    assert usage.calls == [Usage(input_tokens=20, output_tokens=4, complete=True)]


async def test_anthropic_reports_usage_once_a_stream_finishes():
    client = StubAnthropicClient(StubStream(anthropic_events(["a", "b"], 30, 9)))
    usage = UsageLog()
    await collect(
        AnthropicChat("claude-sonnet-5-5", client=client).stream(QUESTION, on_usage=usage)
    )
    assert usage.calls == [Usage(input_tokens=30, output_tokens=9, complete=True)]


async def test_anthropic_closing_the_stream_early_closes_the_sdk_stream():
    sdk_stream = StubStream(anthropic_events(["one ", "two ", "three"], 30, 9))
    usage = UsageLog()
    chat = AnthropicChat("claude-sonnet-5-5", client=StubAnthropicClient(sdk_stream))

    stream = chat.stream(QUESTION, on_usage=usage)
    assert await anext(stream) == "one "
    await stream.aclose()  # what Starlette does when the browser disconnects

    assert sdk_stream.closed
    assert sdk_stream.consumed == 2  # message_start + the first text, nothing after
    # Input tokens are already known from message_start; output never arrived.
    assert usage.calls == [Usage(input_tokens=30, output_tokens=None, complete=False)]


async def test_concurrent_anthropic_streams_report_their_own_usage():
    client = StubAnthropicClient(
        StubStream(anthropic_events(["a", "b", "c"], 100, 10)),
        StubStream(anthropic_events(["x", "y", "z"], 200, 20)),
    )
    chat = AnthropicChat("claude-sonnet-5-5", client=client)
    first, second = UsageLog(), UsageLog()

    async with anyio.create_task_group() as tg:
        tg.start_soon(collect, chat.stream(QUESTION, on_usage=first))
        tg.start_soon(collect, chat.stream(QUESTION, on_usage=second))

    assert {first.calls[0].input_tokens, second.calls[0].input_tokens} == {100, 200}
    assert len(first.calls) == len(second.calls) == 1
    by_input = {u.input_tokens: u.output_tokens for u in first.calls + second.calls}
    assert by_input == {100: 10, 200: 20}


async def test_anthropic_close_closes_the_client():
    client = StubAnthropicClient()
    await AnthropicChat("claude-sonnet-5-5", client=client).aclose()
    assert client.closed


# --- OpenAI -----------------------------------------------------------------------------------


async def test_openai_streams_text_deltas_and_asks_for_usage():
    client = StubOpenAIClient(StubStream(openai_chunks(["Refunds ", None, "", "take 30 days."])))
    chat = OpenAIChat("gpt-test", client=client, max_output_tokens=500)

    deltas = await collect(chat.stream(QUESTION, system="Answer from the documents."))

    assert deltas == ["Refunds ", "take 30 days."]
    request = client.requests[0]
    assert request["model"] == "gpt-test"
    assert request["messages"] == [
        {"role": "system", "content": "Answer from the documents."},
        {"role": "user", "content": "What is the refund window?"},
    ]
    assert request["max_completion_tokens"] == 500
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert "temperature" not in request


async def test_openai_leaves_out_an_empty_system_prompt():
    client = StubOpenAIClient(StubStream(openai_chunks(["ok"])))
    await collect(OpenAIChat("gpt-test", client=client).stream(QUESTION, max_tokens=64))
    assert client.requests[0]["messages"][0]["role"] == "user"
    assert client.requests[0]["max_completion_tokens"] == 64


async def test_openai_reports_usage_from_the_final_chunk():
    client = StubOpenAIClient(StubStream(openai_chunks(["a", "b"], 30, 9)))
    usage = UsageLog()
    await collect(OpenAIChat("gpt-test", client=client).stream(QUESTION, on_usage=usage))
    assert usage.calls == [Usage(input_tokens=30, output_tokens=9, complete=True)]


async def test_openai_complete_returns_text_and_reports_usage():
    usage = UsageLog()
    text = await OpenAIChat("gpt-test", client=StubOpenAIClient()).complete(
        QUESTION, on_usage=usage
    )
    assert text == "Thirty days."
    assert usage.calls == [Usage(input_tokens=20, output_tokens=4, complete=True)]


async def test_openai_closing_the_stream_early_closes_the_sdk_stream():
    sdk_stream = StubStream(openai_chunks(["one ", "two ", "three"]))
    usage = UsageLog()
    stream = OpenAIChat("gpt-test", client=StubOpenAIClient(sdk_stream)).stream(
        QUESTION, on_usage=usage
    )
    assert await anext(stream) == "one "
    await stream.aclose()

    assert sdk_stream.closed
    assert sdk_stream.consumed == 1
    # OpenAI only sends usage in the last chunk, which never came.
    assert usage.calls == [Usage(input_tokens=None, output_tokens=None, complete=False)]


async def test_openai_close_closes_the_client():
    client = StubOpenAIClient()
    await OpenAIChat("gpt-test", client=client).aclose()
    assert client.closed


# --- usage logging ----------------------------------------------------------------------------


async def test_usage_is_logged_without_message_content(caplog: pytest.LogCaptureFixture):
    client = StubAnthropicClient(StubStream(anthropic_events(["Thirty days."], 30, 9)))
    with caplog.at_level(logging.INFO, logger="app.services.llm"):
        await collect(AnthropicChat("claude-sonnet-5-5", client=client).stream(QUESTION))

    [record] = [r for r in caplog.records if r.getMessage() == "llm usage"]
    assert record.levelno == logging.INFO
    assert record.__dict__["provider"] == "anthropic"
    assert record.__dict__["model"] == "claude-sonnet-5-5"
    assert record.__dict__["input_tokens"] == 30
    assert record.__dict__["output_tokens"] == 9
    assert record.__dict__["complete"] is True
    logged = " ".join(str(r.__dict__) for r in caplog.records)
    assert "refund window" not in logged
    assert "Thirty days" not in logged


async def test_a_failing_usage_callback_does_not_break_the_answer():
    def broken(_: Usage) -> None:
        raise RuntimeError("counter is down")

    client = StubAnthropicClient(StubStream(anthropic_events(["fine"])))
    deltas = await collect(
        AnthropicChat("claude-sonnet-5-5", client=client).stream(QUESTION, on_usage=broken)
    )
    assert deltas == ["fine"]


# --- error mapping ----------------------------------------------------------------------------

STATUS_CASES = [
    (400, LLMBadRequestError),
    (401, LLMAuthError),
    (403, LLMAuthError),
    (429, LLMRateLimitError),
    (500, LLMUnavailableError),
    (529, LLMUnavailableError),
]


def anthropic_status_error(status: int) -> anthropic.APIStatusError:
    response = httpx2.Response(status, request=REQUEST, headers={"request-id": "req_123"})
    return anthropic.APIStatusError("provider said no", response=response, body=None)


def openai_status_error(status: int) -> openai.APIStatusError:
    response = httpx2.Response(status, request=REQUEST)
    return openai.APIStatusError("provider said no", response=response, body=None)


@pytest.mark.parametrize(("status", "expected"), STATUS_CASES)
async def test_anthropic_status_errors_map_to_our_types(status: int, expected: type[LLMError]):
    chat = AnthropicChat(
        "claude-sonnet-5-5", client=StubAnthropicClient(error=anthropic_status_error(status))
    )
    with pytest.raises(expected) as excinfo:
        await chat.complete(QUESTION)
    assert isinstance(excinfo.value.__cause__, anthropic.APIStatusError)


@pytest.mark.parametrize(("status", "expected"), STATUS_CASES)
async def test_openai_status_errors_map_to_our_types(status: int, expected: type[LLMError]):
    chat = OpenAIChat("gpt-test", client=StubOpenAIClient(error=openai_status_error(status)))
    with pytest.raises(expected):
        await chat.complete(QUESTION)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (anthropic.APITimeoutError(request=REQUEST), LLMTimeoutError),
        (anthropic.APIConnectionError(request=REQUEST), LLMUnavailableError),
    ],
)
async def test_anthropic_network_errors_map_to_our_types(
    error: Exception, expected: type[LLMError]
):
    chat = AnthropicChat("claude-sonnet-5-5", client=StubAnthropicClient(error=error))
    with pytest.raises(expected):
        await chat.complete(QUESTION)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (openai.APITimeoutError(request=REQUEST), LLMTimeoutError),
        (openai.APIConnectionError(request=REQUEST), LLMUnavailableError),
    ],
)
async def test_openai_network_errors_map_to_our_types(error: Exception, expected: type[LLMError]):
    chat = OpenAIChat("gpt-test", client=StubOpenAIClient(error=error))
    with pytest.raises(expected):
        await chat.complete(QUESTION)


async def test_anthropic_error_before_the_stream_opens_is_mapped_and_reports_no_usage():
    sdk_stream = StubStream([], open_error=anthropic_status_error(429))
    usage = UsageLog()
    chat = AnthropicChat("claude-sonnet-5-5", client=StubAnthropicClient(sdk_stream))
    with pytest.raises(LLMRateLimitError):
        await collect(chat.stream(QUESTION, on_usage=usage))
    assert usage.calls == []


async def test_anthropic_stream_breaking_midway_is_unavailable():
    sdk_stream = StubStream(
        anthropic_events(["partial "])[:2], fail_with=anthropic.APIConnectionError(request=REQUEST)
    )
    usage = UsageLog()
    chat = AnthropicChat("claude-sonnet-5-5", client=StubAnthropicClient(sdk_stream))

    received: list[str] = []
    with pytest.raises(LLMUnavailableError):
        async for delta in chat.stream(QUESTION, on_usage=usage):
            received.append(delta)

    assert received == ["partial "]
    assert usage.calls == [Usage(input_tokens=12, output_tokens=None, complete=False)]


async def test_openai_stream_breaking_midway_is_unavailable():
    sdk_stream = StubStream(
        openai_chunks(["partial "])[:1], fail_with=openai.APIConnectionError(request=REQUEST)
    )
    chat = OpenAIChat("gpt-test", client=StubOpenAIClient(sdk_stream))
    with pytest.raises(LLMUnavailableError):
        await collect(chat.stream(QUESTION))


async def test_errors_do_not_log_the_key(caplog: pytest.LogCaptureFixture):
    chat = AnthropicChat(
        "claude-sonnet-5-5", client=StubAnthropicClient(error=anthropic_status_error(401))
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMAuthError) as excinfo:
        await chat.complete(QUESTION)
    assert FAKE_KEY not in caplog.text
    assert FAKE_KEY not in str(excinfo.value)
    assert any(r.__dict__.get("request_id") == "req_123" for r in caplog.records)


# --- retries, through the real SDK with a mock transport (no network) --------------------------


async def test_real_anthropic_sdk_retries_then_raises_our_error():
    requests_seen = 0

    def always_500(_: httpx2.Request) -> httpx2.Response:
        nonlocal requests_seen
        requests_seen += 1
        return httpx2.Response(
            500,
            headers={"retry-after-ms": "1"},  # keep the backoff tiny so the test stays fast
            json={"type": "error", "error": {"type": "api_error", "message": "boom"}},
        )

    client = anthropic.AsyncAnthropic(
        api_key=FAKE_KEY,
        max_retries=1,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(always_500)),
    )
    chat = AnthropicChat("claude-sonnet-5-5", client=client)

    with pytest.raises(LLMUnavailableError):
        await chat.complete(QUESTION)
    assert requests_seen == 2  # the first try plus one retry
    await chat.aclose()


# --- FakeChat ---------------------------------------------------------------------------------


async def test_fake_chat_streams_words_and_records_calls():
    fake = FakeChat("Refunds take 30 days.")
    deltas = await collect(fake.stream(QUESTION, system="sys", max_tokens=5))
    assert deltas == ["Refunds ", "take ", "30 ", "days."]
    assert "".join(deltas) == "Refunds take 30 days."
    assert fake.calls[0].messages == QUESTION
    assert fake.calls[0].system == "sys"
    assert fake.calls[0].max_tokens == 5


async def test_fake_chat_gives_responses_in_order_then_repeats_the_last():
    fake = FakeChat(["condensed question", "final answer"])
    assert await fake.complete(QUESTION) == "condensed question"
    assert await collect(fake.stream(QUESTION)) == ["final ", "answer"]
    assert await fake.complete(QUESTION) == "final answer"


async def test_fake_chat_can_fail_partway_through_a_stream():
    fake = FakeChat("one two three", error=LLMUnavailableError("down"), error_after=2)
    received: list[str] = []
    with pytest.raises(LLMUnavailableError):
        async for delta in fake.stream(QUESTION):
            received.append(delta)
    assert received == ["one ", "two "]


async def test_fake_chat_reports_usage():
    usage = UsageLog()
    fake = FakeChat("hi", usage=Usage(input_tokens=3, output_tokens=1, complete=True))
    await collect(fake.stream(QUESTION, on_usage=usage))
    await fake.complete(QUESTION, on_usage=usage)
    assert usage.calls == [Usage(3, 1, True), Usage(3, 1, True)]


def test_every_chat_model_satisfies_the_protocol():
    models: list[ChatModel] = [
        FakeChat(),
        AnthropicChat("claude-sonnet-5-5", client=StubAnthropicClient()),
        OpenAIChat("gpt-test", client=StubOpenAIClient()),
    ]
    assert all(m.model_name for m in models)


# --- app wiring -------------------------------------------------------------------------------


def test_app_builds_the_configured_chat_model_at_startup(make_client: Callable[..., Any]):
    client = make_client()
    with client:  # runs the app's startup
        assert isinstance(client.app.state.chat_model, AnthropicChat)


def test_tests_get_the_fake_chat_model_through_the_dependency(make_client: Callable[..., Any]):
    fake = FakeChat("hello")
    client = make_client(chat_model=fake)
    assert client.app.dependency_overrides[get_chat_model]() is fake
