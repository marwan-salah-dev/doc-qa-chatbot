"""An in-process sliding-window rate limiter.

In memory, which is right for the single uvicorn worker this app runs (as `ReplyGuard`); with
several workers it would need shared storage such as Redis. Only used from the event loop
thread (FastAPI runs async dependencies there), so it needs no lock.
"""

import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass

DAY = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class Rule:
    """At most `limit` hits per `window` seconds; a limit of 0 is off."""

    bucket: str
    limit: int
    window: float


class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._windows: dict[str, float] = {}

    def hit(self, key: str, rules: Sequence[Rule]) -> float | None:
        """Record a hit for `key` under every rule, or none if any rule is full.

        Returns None when allowed, else the seconds until the fullest rule has room again.
        """
        now = self._clock()
        wait = 0.0
        active = [rule for rule in rules if rule.limit > 0]
        for rule in active:
            self._windows[rule.bucket] = rule.window
            hits = self._hits.setdefault((rule.bucket, key), deque())
            while hits and hits[0] <= now - rule.window:
                hits.popleft()
            if len(hits) >= rule.limit:
                wait = max(wait, hits[len(hits) - rule.limit] + rule.window - now)
        if wait > 0:
            return wait
        for rule in active:
            self._hits[(rule.bucket, key)].append(now)
        return None

    def prune(self) -> None:
        """Forget clients with no hit left inside their rule's window, so memory stays bounded
        (the cleanup sweep calls this)."""
        now = self._clock()
        idle = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] <= now - self._windows.get(key[0], DAY)
        ]
        for key in idle:
            del self._hits[key]

    def tracked(self) -> int:
        return len(self._hits)
