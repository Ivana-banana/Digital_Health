"""Порты — Протоколы границ (plan §2, §4).

Пайплайн зависит от этих абстракций, не от адаптеров (правило зависимостей —
внутрь). Реализации живут в `adapters/` и внедряются через `Deps`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from src.domain.schemas import PICO, ScreenJudgment, Source

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


@dataclass
class SearchResult:
    """Результат поиска: источники + QueryTranslation (прозрачность поиска, крит. 2)."""

    sources: list[Source]
    translation: str | None = None


class SearchPort(Protocol):
    """Поиск публикаций в источнике (PubMed/EuropePMC/OpenAlex), plan §6."""

    async def search(self, query: str, *, limit: int = 100) -> SearchResult: ...


class ScientometricsPort(Protocol):
    """Наукометрия: цитируемость, venue (OpenAlex), plan §6.1."""

    async def enrich(self, sources: list[Source]) -> list[Source]: ...


class QuartilePort(Protocol):
    """Квартиль журнала по названию (Scimago SJR, офлайн), plan §6.1."""

    def quartile(self, journal: str | None) -> str | None: ...


class ClassifierPort(Protocol):
    """Классификатор дизайна исследования (модель A, обучается в YC), plan §7."""

    async def classify(self, sources: list[Source]) -> list[Source]: ...


class RerankerPort(Protocol):
    """Cross-encoder реранкер query×passage (модель B), plan §6.4.

    Обобщён над текстовыми пассажами (RAG-чанки и `title+abstract` кандидатов). Возвращает
    индексы `passages` в порядке убывания релевантности, не более `top_n`.
    """

    async def rerank(self, query: str, passages: list[str], *, top_n: int) -> list[int]: ...


class ScreeningPort(Protocol):
    """Скрининг-классификатор include/exclude (модель C, обучается в YC), plan §7.

    Порог настроен на **recall ≥ 0.95** — не терять РКИ. Работает как второе мнение поверх
    LLM-скрининга (recall-first): используется, чтобы вернуть ошибочно исключённые РКИ.
    Возвращает суждение на каждый источник (в порядке входа).
    """

    async def screen(self, sources: list[Source], pico: PICO) -> list[ScreenJudgment]: ...


class FullTextPort(Protocol):
    """Загрузка полного текста OA-статьи (Europe PMC), plan §6.4.

    Возвращает тело статьи или None (нет pmcid / не Open Access) — пайплайн деградирует
    на извлечение из абстракта.
    """

    async def fetch(self, source: Source) -> str | None: ...


class VerifierPort(Protocol):
    """Верификация ссылки (DOI/PMID/source_id) против реального источника (plan §9).

    Офлайн — против замороженного корпуса; live — Crossref/PubMed за тем же портом.
    """

    async def verify(self, source_id: str) -> bool: ...
