"""Состояние графа с reducer'ами (plan §4).

Узлы возвращают частичные апдейты, не мутируют state. Списки склеиваются
reducer'ами (`operator.add` / `identity_dedup_reducer`) → нет гонок при fan-out.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from src.domain.identity import identity_dedup_reducer
from src.domain.schemas import (
    PICO,
    Appraisal,
    Claim,
    Event,
    Extraction,
    Infeasible,
    MetaResult,
    PrismaCounts,
    Query,
    Report,
    ScopingSummary,
    ScreenDecision,
    Source,
)


class ResearchState(TypedDict, total=False):
    """Состояние исследовательского пайплайна гипотеза→ответ (plan §3, §4)."""

    raw_hypothesis: str
    pico: PICO | None
    queries: list[Query]
    candidates: Annotated[list[Source], identity_dedup_reducer]
    scoping: ScopingSummary | None
    screening: Annotated[list[ScreenDecision], operator.add]
    prisma: PrismaCounts
    extractions: Annotated[list[Extraction], operator.add]
    appraisals: Annotated[list[Appraisal], operator.add]
    meta: MetaResult | Infeasible | None
    report: Report | None
    provenance: Annotated[list[Claim], operator.add]
    audit: Annotated[list[Event], operator.add]
