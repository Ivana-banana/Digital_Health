"""Пулинг эффектов — fixed-effect inverse-variance + гетерогенность (plan §8).

P2: детерминированный fixed-effect пул в лог-пространстве для ratio-мер, I²/Q.
Random-effects (DerSimonian–Laird) + Hartung-Knapp, Egger и forest/funnel — P3.
Совместимость мер: пулируем только одну меру (нельзя смешивать HR/OR/RR).
"""

from __future__ import annotations

import math

from src.domain.schemas import Appraisal, Extraction, Infeasible, MetaResult
from src.stats.distributions import t_quantile, t_two_sided_p
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


def _largest_compatible_group(
    extractions: list[Extraction],
) -> tuple[str, list[Extraction]] | Infeasible:
    """Наибольшая группа одной меры (нельзя смешивать HR/OR/RR). <2 → структурное Infeasible."""
    groups: dict[str, list[Extraction]] = {}
    for e in poolable(extractions):
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
    return effect_type, grp


def _effects_weights(grp: list[Extraction], *, log: bool) -> tuple[list[float], list[float]]:
    """Точечные оценки (в лог-пространстве для ratio) и fixed-веса 1/SE²."""
    effs = [math.log(e.point) if log else e.point for e in grp]  # type: ignore[arg-type]
    weights = [1 / e.se**2 for e in grp]  # type: ignore[operator]
    return effs, weights


def _heterogeneity(effs: list[float], weights: list[float]) -> tuple[float, float, float]:
    """Q (χ²), I² (%) и τ² по DerSimonian–Laird над fixed-весами."""
    w_sum = sum(weights)
    mu = sum(w * x for w, x in zip(weights, effs, strict=True)) / w_sum
    q_stat = sum(w * (x - mu) ** 2 for w, x in zip(weights, effs, strict=True))
    df = len(effs) - 1
    i_squared = max(0.0, (q_stat - df) / q_stat) * 100 if q_stat > 0 else 0.0
    c = w_sum - sum(w**2 for w in weights) / w_sum
    tau_squared = max(0.0, (q_stat - df) / c) if c > 0 else 0.0
    return q_stat, i_squared, tau_squared


def fixed_effect_pool(extractions: list[Extraction]) -> MetaResult | Infeasible:
    """Пул наибольшей совместимой группы (одна мера). <2 совместимых → структурное Infeasible."""
    sel = _largest_compatible_group(extractions)
    if isinstance(sel, Infeasible):
        return sel
    effect_type, grp = sel

    log = is_log_scale(effect_type)
    effs, weights = _effects_weights(grp, log=log)
    w_sum = sum(weights)
    pooled = sum(w * x for w, x in zip(weights, effs, strict=True)) / w_sum
    se_pool = math.sqrt(1 / w_sum)
    low, high = pooled - Z95 * se_pool, pooled + Z95 * se_pool

    q_stat, i_squared, _ = _heterogeneity(effs, weights)
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


def random_effects_pool(extractions: list[Extraction]) -> MetaResult | Infeasible:
    """Random-effects (DerSimonian–Laird) + HKSJ-поправка ДИ при малом k (plan §8)."""
    sel = _largest_compatible_group(extractions)
    if isinstance(sel, Infeasible):
        return sel
    effect_type, grp = sel

    log = is_log_scale(effect_type)
    effs, weights = _effects_weights(grp, log=log)
    q_stat, i_squared, tau_squared = _heterogeneity(effs, weights)

    # Random-effects веса включают межисследовательскую дисперсию τ².
    rw = [1 / (e.se**2 + tau_squared) for e in grp]  # type: ignore[operator]
    rw_sum = sum(rw)
    pooled = sum(w * x for w, x in zip(rw, effs, strict=True)) / rw_sum

    # HKSJ: масштабированная дисперсия + t-квантиль с df=k−1 (надёжнее при k=2–5).
    df = len(grp) - 1
    se_hksj = math.sqrt(
        sum(w * (x - pooled) ** 2 for w, x in zip(rw, effs, strict=True)) / (df * rw_sum)
    )
    t = t_quantile(df)
    low, high = pooled - t * se_hksj, pooled + t * se_hksj

    if log:
        pooled, low, high = math.exp(pooled), math.exp(low), math.exp(high)

    return MetaResult(
        effect_type=effect_type,  # type: ignore[arg-type]
        outcome=grp[0].outcome,
        k_studies=len(grp),
        pooled_point=pooled,
        pooled_ci_low=low,
        pooled_ci_high=high,
        model="random_hksj",
        i_squared=round(i_squared, 1),
        q_stat=round(q_stat, 3),
        tau_squared=round(tau_squared, 4),
    )


def egger_test(extractions: list[Extraction]) -> float | None:
    """Тест Эггера на асимметрию воронки (смещение публикаций). <10 исследований → None."""
    sel = _largest_compatible_group(extractions)
    if isinstance(sel, Infeasible):
        return None
    effect_type, grp = sel
    if len(grp) < 10:
        return None  # Egger ненадёжен при малом k (plan §8)

    effs, _ = _effects_weights(grp, log=is_log_scale(effect_type))
    ses = [e.se for e in grp]
    # Регрессия стандартного нормального отклонения (effect/SE) на точность (1/SE):
    # значимый интерсепт → асимметрия воронки (эффект малых исследований).
    xs = [1 / s for s in ses]  # type: ignore[operator]
    ys = [eff / s for eff, s in zip(effs, ses, strict=True)]  # type: ignore[operator]
    n = len(grp)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    denom = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    se_intercept = math.sqrt((sse / (n - 2)) * sxx / denom)
    if se_intercept == 0:
        return None
    return t_two_sided_p(intercept / se_intercept, n - 2)


def leave_one_out(extractions: list[Extraction]) -> list[MetaResult]:
    """Чувствительность: пере-пул без каждого исследования группы (нужно ≥3, иначе пусто).

    Каждый MetaResult помечен `excluded_source_id` — какое исследование выведено из пула
    (для UI/отчёта, plan §8 sensitivity).
    """
    sel = _largest_compatible_group(extractions)
    if isinstance(sel, Infeasible):
        return []
    _, grp = sel
    results: list[MetaResult] = []
    for i, excluded in enumerate(grp):
        res = random_effects_pool(grp[:i] + grp[i + 1 :])
        if isinstance(res, MetaResult):
            results.append(res.model_copy(update={"excluded_source_id": excluded.source_id}))
    return results


def sensitivity_by_rob(
    extractions: list[Extraction], appraisals: list[Appraisal]
) -> MetaResult | Infeasible:
    """Чувствительность: пере-пул, исключив исследования с высоким риском смещения (RoB)."""
    high = {a.source_id for a in appraisals if a.overall == "high"}
    return random_effects_pool([e for e in extractions if e.source_id not in high])
