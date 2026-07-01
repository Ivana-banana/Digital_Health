"""Градуированная доказательность по GRADE (plan §8, §9) — чистая функция.

Cochrane-подобная калибровка (GRADE Handbook 2013):
- Start: все РКИ → high, любое наблюдательное → low.
- Downgrade (по одной ступени, суммируются):
  - inconsistency: I² > 50% → −1; I² > 90% → −2 (considerable heterogeneity);
  - imprecision: для ratio-мер CI пересекает линию no-effect (1.0) → −1, либо
    очень широкий CI (upper/lower > 4) → −1;
  - indirectness / low-quality-source: извлечение только из абстрактов → −1;
  - publication bias: значимый Egger (p<0.1) → −1;
  - risk of bias: high-RoB в большинстве исследований → −1.
- Upgrade (для start=low, plan §8):
  - large effect: HR/OR/RR < 0.5 или > 2.0 → +1;
  - very large effect: < 0.2 или > 5.0 → +2 (перекрывает +1).

Downgrades клампятся до very_low, upgrades — до high.
"""

from __future__ import annotations

from src.domain.schemas import GradeLevel, StudyDesign

_LEVELS: list[GradeLevel] = ["high", "moderate", "low", "very_low"]

# Ratio-меры анализируются относительно линии отсутствия эффекта = 1.0.
_RATIO_MEASURES = {"HR", "OR", "RR"}


def _inconsistency_downgrade(i_squared: float | None) -> int:
    """I² > 90% — considerable heterogeneity (Cochrane) → −2; > 50% → −1; иначе 0."""
    if i_squared is None:
        return 0
    if i_squared > 90:
        return 2
    if i_squared > 50:
        return 1
    return 0


def _imprecision_downgrade(ci_low: float, ci_high: float, *, effect_type: str | None) -> int:
    """Ratio-мера: CI пересекает 1.0 (no-effect) → −1; иначе широкий CI (upper/lower>4) → −1."""
    if effect_type in _RATIO_MEASURES and ci_low <= 1.0 <= ci_high:
        return 1
    if ci_low > 0 and ci_high / ci_low > 4:
        return 1
    return 0


def _large_effect_upgrade(pooled_point: float | None, *, effect_type: str | None) -> int:
    """Ratio-мера: <0.2 или >5 → +2 (very large); <0.5 или >2 → +1 (large); иначе 0."""
    if effect_type not in _RATIO_MEASURES or pooled_point is None or pooled_point <= 0:
        return 0
    if pooled_point < 0.2 or pooled_point > 5.0:
        return 2
    if pooled_point < 0.5 or pooled_point > 2.0:
        return 1
    return 0


def grade_level(
    designs: list[StudyDesign],
    *,
    i_squared: float | None,
    ci_low: float,
    ci_high: float,
    abstract_only: bool = True,
    egger_p: float | None = None,
    high_rob: bool = False,
    effect_type: str | None = None,
    pooled_point: float | None = None,
) -> GradeLevel:
    """Уровень доказательности пула по Cochrane-подобной калибровке (plan §8).

    Backward-compat: `effect_type`/`pooled_point` необязательные — без них старая логика
    (I², ширина CI, косвенность, Egger, RoB) работает как раньше.
    """
    start: GradeLevel = "high" if designs and all(d == StudyDesign.RCT for d in designs) else "low"
    start_idx = _LEVELS.index(start)

    downgrades = 0
    downgrades += _inconsistency_downgrade(i_squared)
    downgrades += _imprecision_downgrade(ci_low, ci_high, effect_type=effect_type)
    if abstract_only:
        downgrades += 1  # indirectness / low-quality source: эффекты извлечены из абстрактов
    if egger_p is not None and egger_p < 0.1:
        downgrades += 1  # публикационное смещение (значимый Egger)
    if high_rob:
        downgrades += 1  # высокий риск смещения в большинстве исследований

    # Upgrade применяется только когда start=low (наблюдательные) — Cochrane-guidance.
    upgrades = 0
    if start == "low":
        upgrades = _large_effect_upgrade(pooled_point, effect_type=effect_type)

    idx = max(0, min(len(_LEVELS) - 1, start_idx + downgrades - upgrades))
    return _LEVELS[idx]
