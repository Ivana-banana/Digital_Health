"""Пулинг эффектов — fixed-effect inverse-variance + гетерогенность (plan §8).

P2: детерминированный fixed-effect пул в лог-пространстве для ratio-мер, I²/Q.
Random-effects (DerSimonian–Laird) + Hartung-Knapp, Egger и forest/funnel — P3.
Совместимость мер: пулируем только одну меру (нельзя смешивать HR/OR/RR).
"""

from __future__ import annotations

import math

from src.domain.schemas import Extraction, Infeasible, MetaResult
from src.stats.effect_conversions import Z95, is_log_scale


def poolable(extractions: list[Extraction]) -> list[Extraction]:
    """Исследования с извлекаемой дисперсией (point + положительный SE)."""
    return [
        e
        for e in extractions
        if e.point is not None
        and e.se is not None
        and e.se > 0
        and e.variance_source != "unavailable"
    ]


def fixed_effect_pool(extractions: list[Extraction]) -> MetaResult | Infeasible:
    """Пул наибольшей совместимой группы (одна мера). <2 совместимых → структурное Infeasible."""
    ps = poolable(extractions)
    groups: dict[str, list[Extraction]] = {}
    for e in ps:
        if e.effect_type:
            groups.setdefault(e.effect_type, []).append(e)

    if not groups:
        return Infeasible(
            reason="Нет исследований с извлекаемой дисперсией эффекта.",
            missing=["≥2 исследования с ДИ/SE или 2×2"],
        )

    effect_type, grp = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(grp) < 2:
        return Infeasible(
            reason="Меньше 2 совместимых по мере исследований (нельзя смешивать HR/OR/RR).",
            missing=["≥2 совместимых эффекта одной меры"],
        )

    log = is_log_scale(effect_type)
    effs = [math.log(e.point) if log else e.point for e in grp]  # type: ignore[arg-type]
    weights = [1 / e.se**2 for e in grp]  # type: ignore[operator]
    w_sum = sum(weights)
    pooled = sum(w * x for w, x in zip(weights, effs, strict=True)) / w_sum
    se_pool = math.sqrt(1 / w_sum)
    low, high = pooled - Z95 * se_pool, pooled + Z95 * se_pool

    q_stat = sum(w * (x - pooled) ** 2 for w, x in zip(weights, effs, strict=True))
    df = len(grp) - 1
    i_squared = max(0.0, (q_stat - df) / q_stat) * 100 if q_stat > 0 else 0.0

    if log:
        pooled, low, high = math.exp(pooled), math.exp(low), math.exp(high)

    return MetaResult(
        effect_type=effect_type,  # type: ignore[arg-type]
        outcome=grp[0].outcome,
        k_studies=len(grp),
        pooled_point=pooled,
        pooled_ci_low=low,
        pooled_ci_high=high,
        model="fixed_iv",
        i_squared=round(i_squared, 1),
        q_stat=round(q_stat, 3),
    )
