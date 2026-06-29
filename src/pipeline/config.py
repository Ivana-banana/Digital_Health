"""Конфигурация пайплайна (plan §4): URI моделей AI Studio + флаги качества/глубины.

Одна конфигурация переключает модели и стадии (plan §15). URI — явные, не `/latest`
(модели депрекейтятся с уведомлением, plan §5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ports import ModelRole


@dataclass(frozen=True)
class ModelConfig:
    """URI моделей AI Studio по ролям (plan §5). Меню подтверждено июнь 2026."""

    workhorse: str = "qwen3.6-35b-a3b/latest"  # intake/query/screen/extract/fact-check
    reasoning: str = "qwen3-235b-a22b-fp8/latest"  # appraisal, интерпретация мета, GRADE
    ru: str = "aliceai-llm/latest"  # финальный отчёт (RU)
    long: str = "deepseek-v4-flash/latest"  # long-context синтез по full-text (1M)
    fallback: str = "yandexgpt-5-lite/latest"  # дообучаемый запасной

    def uri(self, role: ModelRole) -> str:
        return getattr(self, role)


@dataclass(frozen=True)
class PipelineConfig:
    """Флаги качества/глубины (plan §4). Деградация фич — через эти переключатели."""

    models: ModelConfig = field(default_factory=ModelConfig)
    vector_backend: str = "faiss"  # faiss | pgvector
    enable_fulltext_mining: bool = False  # OA full-text → RAG/реранкер (качество)
    enable_screening_clf: bool = False  # обученная модель C
    enable_reasoning_escalation: bool = False  # тяжёлые шаги на Qwen3 235B
    eval_mode: str = "frozen"  # frozen | live
    max_deep_studies: int = 15
    llm_max_concurrency: int = 6
