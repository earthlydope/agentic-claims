"""Client-side rate limiting and quota-aware retry for the model provider.

A claims queue cannot be at the mercy of a provider's per-minute quota. Two things are
needed and neither belongs in an agent: a limiter that keeps the platform inside the quota
it has been given, and a retry that honours the delay the provider asks for instead of
hammering it. Both live here, so every agent inherits them.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import Gemini, LlmRequest, LlmResponse

from app.config import MODEL_MAX_RPM, MODEL_RETRY_ATTEMPTS

_WINDOW_SECONDS = 60.0


class RateLimiter:
    """A sliding-window limiter shared by every agent in the process."""

    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max(1, max_per_minute)
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()
        self.waits = 0
        self.total_wait_seconds = 0.0

    async def acquire(self) -> float:
        """Block until a slot is free. Returns how long it waited, in seconds."""
        waited = 0.0
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= _WINDOW_SECONDS:
                    self._calls.popleft()
                if len(self._calls) < self.max_per_minute:
                    self._calls.append(now)
                    return waited
                sleep_for = _WINDOW_SECONDS - (now - self._calls[0]) + 0.05

            self.waits += 1
            self.total_wait_seconds += sleep_for
            waited += sleep_for
            await asyncio.sleep(sleep_for)

    def stats(self) -> dict[str, Any]:
        return {
            "max_per_minute": self.max_per_minute,
            "in_window": len(self._calls),
            "waits": self.waits,
            "total_wait_seconds": round(self.total_wait_seconds, 2),
        }


limiter = RateLimiter(MODEL_MAX_RPM)

_RETRY_DELAY = re.compile(r"retry in ([0-9.]+)s", re.IGNORECASE)
_RETRY_INFO = re.compile(r"'retryDelay':\s*'([0-9.]+)s'")


def is_quota_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "resourceexhausted" in text or "429" in text or "quota" in text


def suggested_delay(exc: BaseException, default: float = 20.0) -> float:
    """Honour the delay the provider asked for, rather than guessing at one."""
    text = str(exc)
    for pattern in (_RETRY_DELAY, _RETRY_INFO):
        match = pattern.search(text)
        if match:
            try:
                return min(60.0, float(match.group(1)) + 0.5)
            except ValueError:
                continue
    return default


class ThrottledGemini(Gemini):
    """Gemini, kept inside the project's quota and patient when it is refused.

    Responses are buffered rather than streamed, because a retry has to be able to start
    the turn again — a half-streamed turn cannot be resumed.
    """

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        last: BaseException | None = None

        for attempt in range(max(1, MODEL_RETRY_ATTEMPTS)):
            await limiter.acquire()
            buffered: list[LlmResponse] = []
            try:
                async for response in super().generate_content_async(llm_request, False):
                    buffered.append(response)
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                last = exc
                if not is_quota_error(exc) or attempt == MODEL_RETRY_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(suggested_delay(exc))
                continue

            for response in buffered:
                yield response
            return

        if last is not None:  # pragma: no cover — the loop either yields or raises
            raise last
