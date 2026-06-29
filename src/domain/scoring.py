"""Trust-скоринг источников (plan §6.3) — чистая функция, без I/O.

`design(35) + quartile(25) + citation(20) + recency(10) + sample(10) − penalties`.
Trust влияет на ПОРЯДОК, GRADE и sensitivity-анализ, **не исключает** (кроме
ретракций) и **не задаёт веса пулинга** (eligibility ≠ trust, plan §6.3).
"""

from __future__ import annotations

import math

from src.domain.schemas import Source, StudyDesign

_DESIGN_POINTS: dict[StudyDesign, float] = {
    StudyDesign.META_ANALYSIS: 35,
    StudyDesign.RCT: 35,
    StudyDesign.NON_RANDOMIZED: 25,
    StudyDesign.OBSERVATIONAL: 18,
    StudyDesign.REVIEW: 15,
    StudyDesign.CASE_REPORT: 5,
    StudyDesign.OTHER: 10,
    StudyDesign.UNKNOWN: 10,
}

_QUARTILE_POINTS: dict[str, float] = {"Q1": 25, "Q2": 18, "Q3": 10, "Q4": 5}


def trust_breakdown(
    source: Source,
    *,
    current_year: int,
    sample_size: int | None = None,
) -> dict[str, float]:
    """Прозрачная разбивка trust по компонентам (для UI-баров и аудита)."""
    design = _DESIGN_POINTS.get(source.design, 10)
    quartile = _QUARTILE_POINTS.get(source.sjr_quartile or "", 8)
    citation = min(20.0, 5.0 * math.log10((source.citations or 0) + 1))

    if source.year is None:
        recency = 2.0
    else:
        age = max(0, current_year - source.year)
        recency = 10.0 if age <= 3 else 7.0 if age <= 5 else 4.0 if age <= 10 else 2.0

    sample = 0.0 if sample_size is None else min(10.0, sample_size / 100.0)
    penalty = 100.0 if source.retracted else 0.0
    return {
        "design": design,
        "quartile": quartile,
        "citation": round(citation, 2),
        "recency": recency,
        "sample": round(sample, 2),
        "penalty": -penalty,
    }


def trust_score(
    source: Source,
    *,
    current_year: int,
    sample_size: int | None = None,
) -> float:
    """Суммарный trust 0–100 (clamp). Ретракция обнуляет балл."""
    bd = trust_breakdown(source, current_year=current_year, sample_size=sample_size)
    return max(0.0, min(100.0, sum(bd.values())))
