"""Rate-limit dependencies for the public demo, keyed on the client IP (see `api.access`)."""

import math
from typing import cast

from fastapi import HTTPException, Request, status

from app.api.access import AccessDep
from app.api.deps import AppSettings
from app.services.limits import DAY, Rule, SlidingWindowLimiter
from app.services.token_budget import TokenBudget

MINUTE = 60
HOUR = 60 * 60


def wait_in_words(seconds: float) -> str:
    if seconds < 90:
        count, unit = max(1, math.ceil(seconds)), "second"
    elif seconds < 90 * MINUTE:
        count, unit = math.ceil(seconds / MINUTE), "minute"
    else:
        count, unit = math.ceil(seconds / HOUR), "hour"
    return f"{count} {unit}{'' if count == 1 else 's'}"


def _enforce(request: Request, key: str, rules: list[Rule], message: str) -> None:
    limiter = cast(SlidingWindowLimiter, request.app.state.limiter)
    wait = limiter.hit(key, rules)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            message.format(wait=wait_in_words(wait)),
            headers={"Retry-After": str(math.ceil(wait))},
        )


async def limit_chat(request: Request, settings: AppSettings, access: AccessDep) -> None:
    if access.restricted:
        rules = [
            Rule("chat-minute", settings.rate_limit_chat_per_minute, MINUTE),
            Rule("chat-day", settings.rate_limit_chat_per_day, DAY),
        ]
        message = "You're asking questions too quickly. Please wait {wait} and try again."
        _enforce(request, access.ip_key, rules, message)


async def limit_uploads(request: Request, settings: AppSettings, access: AccessDep) -> None:
    if access.restricted:
        rules = [Rule("uploads", settings.rate_limit_uploads_per_hour, HOUR)]
        message = "That's a lot of uploads for one hour on this demo. Please wait {wait}."
        _enforce(request, access.ip_key, rules, message)


async def limit_conversations(request: Request, settings: AppSettings, access: AccessDep) -> None:
    if access.restricted:
        rules = [Rule("conversations", settings.rate_limit_conversations_per_hour, HOUR)]
        message = "You've started a lot of chats in the last hour. Please wait {wait}."
        _enforce(request, access.ip_key, rules, message)


async def limit_workspace_creation(
    request: Request, settings: AppSettings, access: AccessDep
) -> None:
    if access.restricted:
        limit = settings.visitor_workspaces_per_ip
        rules = [Rule("workspaces", limit, DAY)]
        message = (
            f"This demo allows {limit} workspaces a day per visitor (deleting one doesn't free "
            "a slot). Please try again in {wait}."
        )
        _enforce(request, access.ip_key, rules, message)


DAILY_CAP_REACHED = (
    "The demo has reached its daily question limit. Please try again tomorrow (in about {wait})."
)


async def check_token_budget(request: Request) -> None:
    """Refuse a question once today's LLM tokens are used up (the cap is 0 unless public)."""
    budget = cast(TokenBudget, request.app.state.token_budget)
    if budget.exhausted():
        wait = budget.seconds_until_reset()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            DAILY_CAP_REACHED.format(wait=wait_in_words(wait)),
            headers={"Retry-After": str(math.ceil(wait))},
        )
