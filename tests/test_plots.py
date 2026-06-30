"""Тесты forest/funnel-плотов (plan §8) — офлайн (Agg), проверяем валидный PNG."""

from pathlib import Path

from src.domain.schemas import Extraction
from src.stats.effect_conversions import derive_variance
from src.stats.meta import random_effects_pool
from src.stats.plots import forest_plot, funnel_plot

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _hr(point, lo, hi, sid):
    return derive_variance(
        Extraction(
            source_id=sid, effect_type="HR", point=point, ci_low=lo, ci_high=hi, outcome="OS"
        )
    )


def _studies():
    return [_hr(0.58, 0.44, 0.77, "a"), _hr(0.63, 0.50, 0.80, "b"), _hr(0.70, 0.55, 0.89, "c")]


def test_forest_plot_writes_valid_png(tmp_path):
    result = random_effects_pool(_studies())
    data = Path(forest_plot(result, _studies(), tmp_path / "forest.png")).read_bytes()
    assert data[:8] == PNG_MAGIC and len(data) > 1000


def test_funnel_plot_writes_valid_png(tmp_path):
    data = Path(funnel_plot(_studies(), tmp_path / "funnel.png")).read_bytes()
    assert data[:8] == PNG_MAGIC and len(data) > 1000
