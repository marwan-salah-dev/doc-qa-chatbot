"""The public demo's daily cap on LLM tokens, shared by every chat.

Totals are kept per UTC day in `llm_usage_days`, so a restart doesn't hand out a fresh
allowance. Usage is only known after each LLM call, so the cap is checked before a question
starts and the last questions of a day can overshoot it a little; set DAILY_TOKEN_CAP below the
provider's own quota to leave room for that.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import LlmUsageDay
from app.services.llm import Usage


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TokenBudget:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        cap: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.cap = cap  # 0 = no cap
        self._session_factory = session_factory
        self._clock = clock
        self._day = ""
        self._used = 0

    def _today(self) -> str:
        return self._clock().date().isoformat()

    def used_today(self) -> int:
        day = self._today()
        if day != self._day:
            with self._session_factory() as db:
                row = db.get(LlmUsageDay, day)
                self._day, self._used = day, row.tokens if row else 0
        return self._used

    def exhausted(self) -> bool:
        return self.cap > 0 and self.used_today() >= self.cap

    def record(self, usage: Usage) -> None:
        """An `on_usage` callback: add one LLM call's tokens to today's total."""
        tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        if not tokens:
            return
        self.used_today()  # loads the day, or rolls over to a new one
        statement = insert(LlmUsageDay).values(day=self._day, tokens=tokens)
        statement = statement.on_conflict_do_update(
            index_elements=[LlmUsageDay.day], set_={"tokens": LlmUsageDay.tokens + tokens}
        )
        with self._session_factory() as db:
            db.execute(statement)
            db.commit()
        self._used += tokens

    def seconds_until_reset(self) -> float:
        now = self._clock()
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
        return (midnight - now).total_seconds()
