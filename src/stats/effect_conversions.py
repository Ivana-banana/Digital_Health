"""Детерминированные конверсии эффектов (plan §0.2, §8).

Восстанавливают дисперсию там, где LLM её не сообщил числом, и кратно расширяют
пул пулируемых исследований. Для ratio-мер (HR/OR/RR) работаем в лог-пространстве.
Контракт: вход — `Extraction` от Extractor (может содержать ДИ / 2×2 / готовый SE);
выход — `Extraction` с заполненными `se`/`point` и честным `variance_source`.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from src.domain.schemas import Extraction

# Квантиль стандартного нормального для 95% ДИ (двусторонний).
Z95 = NormalDist().inv_cdf(0.975)

RATIO_MEASURES = {"HR", "OR", "RR"}


def is_log_scale(effect_type: str | None) -> bool:
    """Ratio-меры анализируются в лог-пространстве, разностные (MD/SMD) — линейно."""
    return effect_type in RATIO_MEASURES


def se_from_ci(low: float, high: float, *, log_scale: bool) -> float:
    """SE точечной оценки из 95% ДИ (в лог-пространстве для ratio-мер)."""
    if log_scale:
        return (math.log(high) - math.log(low)) / (2 * Z95)
    return (high - low) / (2 * Z95)


def se_from_p(estimate: float, p: float, *, log_scale: bool) -> float:
    """SE из двустороннего p-value и точечной оценки (z-аппроксимация)."""
    if not 0 < p < 1:
        raise ValueError("p должно быть в (0, 1)")
    z = NormalDist().inv_cdf(1 - p / 2)
    eff = math.log(estimate) if log_scale else estimate
    return abs(eff) / z


def _corrected_cells(a: float, b: float, c: float, d: float) -> tuple[float, float, float, float]:
    """Коррекция Haldane–Anscombe (+0.5) при нулевой ячейке 2×2."""
    if 0 in (a, b, c, d):
        return a + 0.5, b + 0.5, c + 0.5, d + 0.5
    return a, b, c, d


def or_from_2x2(events1: int, n1: int, events2: int, n2: int) -> tuple[float, float]:
    """Из 2×2 → (logOR, SE(logOR)) с Woolf-SE и коррекцией нулевой ячейки."""
    a, b, c, d = _corrected_cells(events1, n1 - events1, events2, n2 - events2)
    log_or = math.log((a * d) / (b * c))
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return log_or, se


def rr_from_2x2(events1: int, n1: int, events2: int, n2: int) -> tuple[float, float]:
    """Из 2×2 → (logRR, SE(logRR)) с коррекцией нулевой ячейки."""
    a, b, c, d = _corrected_cells(events1, n1 - events1, events2, n2 - events2)
    r1, r2 = a / (a + b), c / (c + d)
    log_rr = math.log(r1 / r2)
    se = math.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    return log_rr, se


def derive_variance(ex: Extraction) -> Extraction:
    """Дозаполнить SE/point и проставить `variance_source`. Не угадывает — иначе `unavailable`."""
    log_scale = is_log_scale(ex.effect_type)

    if ex.se is not None and ex.se > 0:
        return ex.model_copy(update={"variance_source": "reported_se"})

    if ex.point is not None and ex.ci_low and ex.ci_high and ex.ci_low > 0 and ex.ci_high > 0:
        se = se_from_ci(ex.ci_low, ex.ci_high, log_scale=log_scale)
        return ex.model_copy(update={"se": se, "variance_source": "reported_ci"})

    have_2x2 = None not in (ex.events1, ex.n_arm1, ex.events2, ex.n_arm2)
    if have_2x2 and ex.effect_type in ("OR", "RR"):
        fn = or_from_2x2 if ex.effect_type == "OR" else rr_from_2x2
        log_eff, se = fn(ex.events1, ex.n_arm1, ex.events2, ex.n_arm2)
        return ex.model_copy(
            update={"point": math.exp(log_eff), "se": se, "variance_source": "derived_2x2"}
        )

    return ex.model_copy(update={"variance_source": "unavailable"})
