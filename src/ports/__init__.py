"""Порты — Протоколы границ (plan §2, §4).

Пайплайн зависит от этих абстракций, не от адаптеров (правило зависимостей —
внутрь). Реализации живут в `adapters/` и внедряются через `Deps`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from src.domain.schemas import Source

T = TypeVar("T", bound=BaseModel)

# Роль модели → конкретный URI выбирается в адаптере по PipelineConfig (plan §5).
ModelRole = Literal["workhorse", "reasoning", "ru", "long", "fallback"]

# Сообщение в OpenAI-совместимом формате.
Message = dict[str, str]


@dataclass
class Ok(Generic[T]):
    """Успешный типизированный исход LLM-вызова."""

    value: T


@dataclass
class SchemaError:
    """Провал валидации схемы — это результат, а не исключение (для retry/деградации)."""

    reason: str
    raw: str = ""


# Текстовый (бессхемный) исход LLM, когда schema=None.
@dataclass
class Text:
    """Свободный текст от LLM, когда структура не запрашивалась."""

    content: str


class LLMPort(Protocol):
    """OpenAI-совместимый LLM за портом → модель свопается сменой URI (plan §5)."""

    async def complete(
        self,
        msgs: list[Message],
        *,
        schema: type[T] | None = None,
        temperature: float = 0.0,
        model_role: ModelRole = "workhorse",
    ) -> Ok[T] | Text | SchemaError: ...


class SearchPort(Protocol):
    """Поиск публикаций в источнике (PubMed/EuropePMC/OpenAlex), plan §6."""

    async def search(self, query: str, *, limit: int = 100) -> list[Source]: ...


class ScientometricsPort(Protocol):
    """Наукометрия: цитируемость, квартиль журнала, флаг ретракции (plan §6.3)."""

    async def enrich(self, sources: list[Source]) -> list[Source]: ...


class ClassifierPort(Protocol):
    """Классификатор дизайна исследования (модель A, обучается в YC), plan §7."""

    async def classify(self, sources: list[Source]) -> list[Source]: ...


class RerankerPort(Protocol):
    """Реранкер-приоритизатор кандидатов (модель B), plan §6.4."""

    async def rerank(self, query: str, sources: list[Source], *, top_n: int) -> list[Source]: ...


@dataclass
class RateLimiter:
    """Ограничитель частоты per-host (token-bucket). В P0 — заглушка-контракт."""

    rps: float = 10.0


@dataclass
class Limiters:
    """Ограничители конкурентности из `Deps` (plan §3): семафор LLM + лимитеры хостов."""

    llm_max_concurrency: int = 6
    per_host: dict[str, RateLimiter] = field(default_factory=dict)
