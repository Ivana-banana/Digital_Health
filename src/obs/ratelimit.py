"""Ограничители частоты per-host (plan §3).

Token-bucket против 429 на NCBI (10 rps) и polite-pool OpenAlex. Чистая логика
пополнения (`_take`) тестируется без сна с инъекцией часов; `acquire()` —
async-обёртка с реальным ожиданием. Семафор конкурентности LLM живёт в `Deps`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


class RateLimiter:
    """Token-bucket: ≤`rate` операций в секунду, всплеск до `capacity`."""

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.rate = rate
        self.capacity = capacity if capacity is not None else rate
        self.tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    def _take(self, now: float) -> float:
        """Пополнить по времени; есть токен — снять и вернуть 0, иначе вернуть ожидание (с)."""
        elapsed = now - self._updated
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self._updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return 0.0
        return (1 - self.tokens) / self.rate

    async def acquire(self) -> None:
        """Дождаться доступного токена и снять его (потокобезопасно в рамках event loop)."""
        async with self._lock:
            wait = self._take(self._clock())
            if wait > 0:
                await self._sleep(wait)
                self._take(self._clock())


@dataclass
class Limiters:
    """Ограничители из `Deps`: семафор LLM + token-bucket'ы по хостам (plan §3, §4)."""

    llm_max_concurrency: int = 6
    per_host: dict[str, RateLimiter] = field(default_factory=dict)

    def host(self, name: str, rate: float) -> RateLimiter:
        """Вернуть лимитер хоста, создав его с заданным `rate` при первом обращении."""
        if name not in self.per_host:
            self.per_host[name] = RateLimiter(rate)
        return self.per_host[name]
