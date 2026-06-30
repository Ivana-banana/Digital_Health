"""Градуированная доказательность по GRADE (plan §8, §9) — чистая функция.

Старт по дизайну (РКИ=high, наблюдательные=low), затем понижение за несогласованность
(I²), неточность (ширина ДИ), косвенность (извлечение только из абстракта),
публикационное смещение (значимый Egger) и высокий риск смещения (RoB).
"""

from __future__ import annotations

from src.domain.schemas import GradeLevel, StudyDesign

_LEVELS: list[GradeLevel] = ["high", "moderate", "low", "very_low"]


def grade_level(
    designs: list[StudyDesign],
    *,
    i_squared: float | None,
    ci_low: float,
    ci_high: float,
    abstract_only: bool = True,
    egger_p: float | None = None,
    high_rob: bool = False,
) -> GradeLevel:
    """Уровень доказательности пула. Понижения суммируются и клампятся до very_low."""
    start: GradeLevel = "high" if designs and all(d == StudyDesign.RCT for d in designs) else "low"
    downgrades = 0
    if i_squared is not None and i_squared > 50:
        downgrades += 1  # несогласованность
    if ci_low > 0 and ci_high / ci_low > 3:
        downgrades += 1  # неточность (широкий ДИ)
    if abstract_only:
        downgrades += 1  # косвенность: эффекты извлечены из абстрактов
    if egger_p is not None and egger_p < 0.1:
        downgrades += 1  # публикационное смещение (значимый Egger)
    if high_rob:
        downgrades += 1  # высокий риск смещения в большинстве исследований

    idx = min(len(_LEVELS) - 1, _LEVELS.index(start) + downgrades)
    return _LEVELS[idx]
