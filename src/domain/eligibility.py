"""Детерминированный eligibility-скрининг → причина PRISMA (plan §6.3).

Eligibility ≠ Trust: здесь решаем вкл./искл. по надёжным сигналам (ретракция,
тип исследования, грубая релевантность PICO). Причина — из фиксированного enum.
Тонкий семантический скрининг — за LLM-узлом (🔵) поверх этого фильтра.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.identity import identity_key
from src.domain.schemas import PICO, ScreenDecision, Source, StudyDesign


@dataclass
class EligibilityCriteria:
    """Критерии отбора. Пустые поля = ограничение не применяется."""

    allowed_designs: set[StudyDesign] | None = None
    require_terms: bool = False  # проверять присутствие терминов PICO в тексте


def _text(source: Source) -> str:
    return f"{source.title} {source.abstract or ''}".lower()


def screen_source(
    source: Source,
    pico: PICO | None,
    criteria: EligibilityCriteria | None = None,
) -> ScreenDecision:
    """Вернуть решение по одному источнику с причиной исключения (enum) при отказе."""
    crit = criteria or EligibilityCriteria()
    sid = identity_key(source)

    if source.retracted:
        return ScreenDecision(source_id=sid, include=False, reason="retracted")

    if crit.allowed_designs is not None and source.design not in crit.allowed_designs:
        return ScreenDecision(source_id=sid, include=False, reason="wrong_study_type")

    if crit.require_terms and pico is not None:
        text = _text(source)
        if pico.intervention and pico.intervention.lower() not in text:
            return ScreenDecision(source_id=sid, include=False, reason="wrong_intervention")
        if pico.outcome and pico.outcome.lower() not in text:
            return ScreenDecision(source_id=sid, include=False, reason="wrong_outcome")

    return ScreenDecision(source_id=sid, include=True)


@dataclass
class PrismaTally:
    """Аккумулятор причин исключения для диаграммы PRISMA."""

    excluded_by_reason: dict[str, int] = field(default_factory=dict)

    def add(self, decision: ScreenDecision) -> None:
        if not decision.include and decision.reason:
            self.excluded_by_reason[decision.reason] = (
                self.excluded_by_reason.get(decision.reason, 0) + 1
            )
