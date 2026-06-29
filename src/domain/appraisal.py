"""Выбор инструмента оценки качества по дизайну (plan §8) — чистая функция.

RoB 2.0 для РКИ, ROBINS-I для нерандомизированных интервенционных, STROBE для
наблюдательных (plan §8, task-03). P2-базис: правильный инструмент + стандартный
список доменов, инициализированных `unclear` (честно: не оценено детально).
Доменные суждения по существу заполняет LLM-апрейзер (reasoning) — апгрейд P3.
"""

from __future__ import annotations

from src.domain.schemas import Appraisal, StudyDesign

_TOOL_BY_DESIGN: dict[StudyDesign, str] = {
    StudyDesign.RCT: "rob2",
    StudyDesign.NON_RANDOMIZED: "robins_i",
    StudyDesign.OBSERVATIONAL: "strobe",
    StudyDesign.CASE_REPORT: "strobe",
}

_DOMAINS: dict[str, list[str]] = {
    "rob2": [
        "randomization",
        "deviations",
        "missing_data",
        "measurement",
        "selection_of_result",
    ],
    "robins_i": [
        "confounding",
        "selection",
        "classification",
        "deviations",
        "missing_data",
        "measurement",
        "selection_of_result",
    ],
    "strobe": ["reporting_completeness"],
}


def tool_for(design: StudyDesign) -> str:
    """Подобрать шкалу оценки качества под дизайн (по умолчанию RoB 2.0)."""
    return _TOOL_BY_DESIGN.get(design, "rob2")


def appraise_baseline(source_id: str, design: StudyDesign) -> Appraisal:
    """Структурный каркас оценки: верный инструмент + домены = `unclear` (не оценено)."""
    tool = tool_for(design)
    return Appraisal(
        source_id=source_id,
        tool=tool,
        domain_judgements={d: "unclear" for d in _DOMAINS[tool]},
        overall="some_concerns",
    )
