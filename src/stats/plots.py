"""Forest- и funnel-плоты мета-анализа (plan §8) — matplotlib на Agg (офлайн).

Бэкенд Agg выбирается до импорта pyplot → нет дисплея/сети (docker/CI, plan §12).
Per-study ДИ восстанавливаются из point+SE в той же шкале, что и пулинг.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # офлайн-бэкенд без дисплея (docker/CI)

import matplotlib.pyplot as plt  # noqa: E402

from src.domain.schemas import Extraction, MetaResult  # noqa: E402
from src.stats.effect_conversions import Z95, is_log_scale  # noqa: E402


def _study_ci(point: float, se: float, *, log: bool) -> tuple[float, float]:
    """95% ДИ исследования из точки и SE (в лог-пространстве для ratio-мер)."""
    if log:
        return math.exp(math.log(point) - Z95 * se), math.exp(math.log(point) + Z95 * se)
    return point - Z95 * se, point + Z95 * se


def _poolable(studies: list[Extraction]) -> list[Extraction]:
    return [e for e in studies if e.point is not None and e.se is not None and e.se > 0]


def forest_plot(result: MetaResult, studies: list[Extraction], path: str | Path) -> str:
    """Forest plot: оценки исследований + ромб пула. Возвращает путь к PNG."""
    log = is_log_scale(result.effect_type)
    rows = _poolable(studies)
    ys = list(range(len(rows), 0, -1))  # сверху вниз

    fig, ax = plt.subplots(figsize=(7, 0.5 * len(rows) + 1.5))
    for y, e in zip(ys, rows, strict=True):
        lo, hi = _study_ci(e.point, e.se, log=log)  # type: ignore[arg-type]
        ax.plot([lo, hi], [y, y], color="black")
        ax.plot(e.point, y, "s", color="steelblue")

    ax.plot([result.pooled_ci_low, result.pooled_ci_high], [0, 0], color="firebrick", lw=2)
    ax.plot(result.pooled_point, 0, "D", color="firebrick")

    if log:
        ax.set_xscale("log")
    ax.axvline(1.0 if log else 0.0, ls="--", color="gray")  # линия отсутствия эффекта
    ax.set_yticks([0, *ys])
    ax.set_yticklabels(["Pooled", *[e.source_id for e in rows]])
    ax.set_xlabel(f"{result.effect_type} (95% CI)")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return str(path)


def funnel_plot(studies: list[Extraction], path: str | Path) -> str:
    """Funnel plot: эффект против SE (точные оценки сверху). Возвращает путь к PNG."""
    rows = _poolable(studies)
    log = is_log_scale(rows[0].effect_type) if rows else False

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter([e.point for e in rows], [e.se for e in rows], color="steelblue")
    if log:
        ax.set_xscale("log")
    ax.invert_yaxis()  # малый SE (точные исследования) — сверху
    ax.set_xlabel("Effect")
    ax.set_ylabel("Standard error")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return str(path)
