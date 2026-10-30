"""Per-IP rate limits on the public demo: 429 with Retry-After and a message people can read."""

import uuid
from collections.abc import Callable

import pytest
from chat_helpers import CITED_REPLY, MIN_SCORE, OFF_TOPIC
from fastapi.testclient import TestClient

from app.api.access import client_key
from app.services.limits import Rule, SlidingWindowLimiter
from app.services.llm import FakeChat

VISITOR = {"X-Visitor-Id": str(uuid.uuid4())}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- The limiter -----------------------------------------------------------------------------


def test_the_window_slides_and_says_how_long_to_wait() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(clock)
    rule = Rule("chat", limit=2, window=60)

    assert limiter.hit("1.2.3.4", [rule]) is None
    clock.now += 10
    assert limiter.hit("1.2.3.4", [rule]) is None
    clock.now += 5
    assert limiter.hit("1.2.3.4", [rule]) == pytest.approx(45)  # the first hit leaves at 60
    assert limiter.hit("5.6.7.8", [rule]) is None  # other clients are unaffected

    clock.now += 45
    assert limiter.hit("1.2.3.4", [rule]) is None


def test_a_refused_hit_counts_against_no_rule() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(clock)
    minute, day = Rule("m", limit=1, window=60), Rule("d", limit=3, window=86400)

    assert limiter.hit("ip", [minute, day]) is None
    for _ in range(5):  # refused by the minute rule: the day rule must not fill up meanwhile
        assert limiter.hit("ip", [minute, day]) is not None
    clock.now += 60
    assert limiter.hit("ip", [minute, day]) is None


def test_a_zero_limit_is_off() -> None:
    limiter = SlidingWindowLimiter(Clock())

    assert all(limiter.hit("ip", [Rule("x", limit=0, window=60)]) is None for _ in range(100))


def test_prune_forgets_idle_clients() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("ip", [Rule("x", limit=5, window=60)])

    clock.now += 61
    limiter.prune()

    assert limiter.tracked() == 0


def test_ipv6_clients_are_keyed_by_their_64() -> None:
    assert client_key("2001:db8:1:2:aaaa::1") == client_key("2001:db8:1:2:ffff::9")
    assert client_key("2001:db8:1:2::1") != client_key("2001:db8:1:3::1")
    assert client_key("203.0.113.7") == "203.0.113.7"


# --- The API ---------------------------------------------------------------------------------


@pytest.fixture
def demo_factory(make_client: Callable[..., TestClient]) -> Callable[..., TestClient]:
    def factory(**overrides: object) -> TestClient:
        return make_client(
            public_demo=True,
            rag_min_score=MIN_SCORE,
            chat_model=FakeChat(CITED_REPLY),
            **overrides,
        )

    return factory


def test_too_many_questions_get_a_friendly_429(demo_factory: Callable[..., TestClient]) -> None:
    client = demo_factory(rate_limit_chat_per_minute=2)
    ws = client.post("/workspaces", json={"name": "Mine"}, headers=VISITOR).json()["id"]
    conv = client.post(f"/workspaces/{ws}/conversations", headers=VISITOR).json()["id"]
    url = f"/workspaces/{ws}/conversations/{conv}/messages"

    for _ in range(2):
        assert client.post(url, json={"question": OFF_TOPIC}, headers=VISITOR).status_code == 200
    response = client.post(url, json={"question": OFF_TOPIC}, headers=VISITOR)

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert "too quickly" in response.json()["detail"]
    # A new visitor id from the same IP doesn't reset it: limits follow the IP
    other = {"X-Visitor-Id": str(uuid.uuid4())}
    ws2 = client.post("/workspaces", json={"name": "Mine"}, headers=other).json()["id"]
    conv2 = client.post(f"/workspaces/{ws2}/conversations", headers=other).json()["id"]
    url2 = f"/workspaces/{ws2}/conversations/{conv2}/messages"
    assert client.post(url2, json={"question": OFF_TOPIC}, headers=other).status_code == 429


def test_uploads_are_limited(demo_factory: Callable[..., TestClient]) -> None:
    client = demo_factory(rate_limit_uploads_per_hour=1)
    ws = client.post("/workspaces", json={"name": "Mine"}, headers=VISITOR).json()["id"]

    def upload(content: bytes):
        file = ("a.txt", content, "text/plain")
        return client.post(f"/workspaces/{ws}/documents", files={"file": file}, headers=VISITOR)

    assert upload(b"one").status_code == 202
    response = upload(b"two")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_new_conversations_are_limited(demo_factory: Callable[..., TestClient]) -> None:
    client = demo_factory(rate_limit_conversations_per_hour=1)
    ws = client.post("/workspaces", json={"name": "Mine"}, headers=VISITOR).json()["id"]

    assert client.post(f"/workspaces/{ws}/conversations", headers=VISITOR).status_code == 201
    assert client.post(f"/workspaces/{ws}/conversations", headers=VISITOR).status_code == 429


def test_each_ip_can_create_a_few_workspaces_a_day(demo_factory: Callable[..., TestClient]) -> None:
    client = demo_factory(visitor_workspaces_per_ip=2)

    for _ in range(2):
        assert client.post("/workspaces", json={"name": "W"}, headers=VISITOR).status_code == 201
    response = client.post("/workspaces", json={"name": "W"}, headers=VISITOR)

    assert response.status_code == 429
    assert "2 workspaces" in response.json()["detail"]
    assert int(response.headers["Retry-After"]) > 3600


def test_the_admin_and_private_deployments_are_not_limited(
    make_client: Callable[..., TestClient],
) -> None:
    admin = make_client(public_demo=True, admin_api_key="k", visitor_workspaces_per_ip=1)
    for _ in range(3):
        response = admin.post("/workspaces", json={"name": "W"}, headers={"X-Admin-Key": "k"})
        assert response.status_code == 201

    private = make_client(visitor_workspaces_per_ip=1)
    for _ in range(3):
        assert private.post("/workspaces", json={"name": "W"}).status_code == 201
