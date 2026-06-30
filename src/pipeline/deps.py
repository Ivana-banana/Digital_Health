"""Внедрённые зависимости пайплайна (plan §4).

`Deps` несёт порты + ограничители + кэш + логгер. Узлы получают `Deps`, но об
ограничителях не знают — те живут в адаптерах/`Deps` (правило зависимостей).
Опциональные порты (search/scientometrics/...) = None в P0: узлы деградируют.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from src.obs.logging import StructuredLogger, get_logger
from src.obs.ratelimit import Limiters
from src.pipeline.config import PipelineConfig
from src.ports import (
    ClassifierPort,
    LLMPort,
    QuartilePort,
    RerankerPort,
    ScientometricsPort,
    SearchPort,
    VerifierPort,
)


@dataclass
class Deps:
    """DI-контейнер: порты + ограничители + кэш + логгер (plan §4)."""

    llm: LLMPort
    config: PipelineConfig = field(default_factory=PipelineConfig)
    search: SearchPort | None = None
    scientometrics: ScientometricsPort | None = None
    scimago: QuartilePort | None = None
    classifier: ClassifierPort | None = None
    reranker: RerankerPort | None = None
    verifier: VerifierPort | None = None
    limiters: Limiters = field(default_factory=Limiters)
    cache: dict[str, object] = field(default_factory=dict)
    logger: StructuredLogger = field(default_factory=lambda: get_logger("pipeline"))
    _llm_semaphore: asyncio.Semaphore | None = field(default=None, repr=False)

    @property
    def llm_semaphore(self) -> asyncio.Semaphore:
        """Семафор конкурентности LLM-вызовов (создаётся лениво в текущем event loop)."""
        if self._llm_semaphore is None:
            self._llm_semaphore = asyncio.Semaphore(self.config.llm_max_concurrency)
        return self._llm_semaphore
