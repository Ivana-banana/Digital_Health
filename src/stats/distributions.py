"""Числовые распределения для мета-анализа (plan §8) — чистый stdlib, без scipy.

Нужен только двусторонний 95% t-критический для HKSJ-поправки ДИ при малом k
(аналог `Z95` из `effect_conversions`). Реализован через инверсию t-CDF, которая
выражается регуляризованной неполной бета-функцией (Numerical Recipes `betai`).
"""

from __future__ import annotations

import math


def _betacf(a: float, b: float, x: float) -> float:
    """Непрерывная дробь для неполной бета-функции (Lentz)."""
    fpmin, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        for aa in (
            m * (b - m) * x / ((qam + m2) * (a + m2)),
            -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2)),
        ):
            d = 1.0 + aa * d
            if abs(d) < fpmin:
                d = fpmin
            d = 1.0 / d
            c = 1.0 + aa / c
            if abs(c) < fpmin:
                c = fpmin
            h *= d * c
        if abs(d * c - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Регуляризованная неполная бета-функция I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbt + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _t_cdf(t: float, df: int) -> float:
    """Функция распределения Стьюдента в точке t (df степеней свободы)."""
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def t_quantile(df: int) -> float:
    """Двусторонний 95% t-критический (97.5-й перцентиль) — бисекция по t-CDF."""
    lo, hi = 0.0, 1000.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _t_cdf(mid, df) < 0.975:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def t_two_sided_p(t_stat: float, df: int) -> float:
    """Двусторонний p-value для t-статистики (df степеней свободы) — для теста Эггера."""
    return 2.0 * (1.0 - _t_cdf(abs(t_stat), df))
