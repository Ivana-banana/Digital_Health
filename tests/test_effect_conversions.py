"""Табличные тесты конверсий эффектов (plan §8) — без сети, детерминированно."""

import math

from src.domain.schemas import Extraction
from src.stats.effect_conversions import (
    derive_variance,
    is_plausible_effect,
    or_from_2x2,
    rr_from_2x2,
    se_from_ci,
    se_from_p,
)


def test_se_from_ci_log_scale_hr():
    # HR 0.58 (95% CI 0.44–0.77): SE(logHR) ≈ 0.143
    se = se_from_ci(0.44, 0.77, log_scale=True)
    assert abs(se - 0.1428) < 1e-3


def test_se_from_ci_linear():
    se = se_from_ci(1.0, 5.0, log_scale=False)
    assert abs(se - (4.0 / (2 * 1.959963984540054))) < 1e-9


def test_or_from_2x2_known_value():
    log_or, se = or_from_2x2(10, 100, 20, 100)
    assert abs(math.exp(log_or) - 0.4444) < 1e-3
    assert abs(se - 0.4167) < 1e-3


def test_zero_cell_correction_is_finite():
    log_or, se = or_from_2x2(0, 10, 5, 10)
    assert math.isfinite(log_or) and math.isfinite(se)


def test_rr_from_2x2_known_value():
    log_rr, se = rr_from_2x2(10, 100, 20, 100)
    assert abs(math.exp(log_rr) - 0.5) < 1e-3
    assert se > 0


def test_se_from_p():
    # estimate=1 (logHR=0) даёт SE 0 — берём ненулевой эффект
    se = se_from_p(0.5, 0.05, log_scale=True)
    assert se > 0


def test_derive_variance_from_ci():
    ex = Extraction(source_id="s1", effect_type="HR", point=0.58, ci_low=0.44, ci_high=0.77)
    out = derive_variance(ex)
    assert out.variance_source == "reported_ci"
    assert out.se and abs(out.se - 0.1428) < 1e-3


def test_derive_variance_from_2x2():
    ex = Extraction(
        source_id="s2", effect_type="OR", n_arm1=100, n_arm2=100, events1=10, events2=20
    )
    out = derive_variance(ex)
    assert out.variance_source == "derived_2x2"
    assert out.point and abs(out.point - 0.4444) < 1e-3
    assert out.se and out.se > 0


def test_derive_variance_unavailable_when_nothing():
    ex = Extraction(source_id="s3", effect_type="HR", point=0.7)
    out = derive_variance(ex)
    assert out.variance_source == "unavailable"
    assert out.se is None


def test_reported_se_preserved():
    ex = Extraction(source_id="s4", effect_type="HR", point=0.7, se=0.2)
    out = derive_variance(ex)
    assert out.variance_source == "reported_se"
    assert out.se == 0.2


# --- Гардрейл правдоподобия точечной оценки (plan §9) ---


def test_is_plausible_effect_ratio_ok():
    for p in (0.05, 0.5, 1.0, 2.0, 20.0):
        assert is_plausible_effect(Extraction(source_id="x", effect_type="HR", point=p))


def test_is_plausible_effect_ratio_rejects_out_of_band():
    # Реальный мисрид live-прогона: `HR 0.016` — резать. Симметрично, HR=25 — резать.
    assert not is_plausible_effect(Extraction(source_id="x", effect_type="HR", point=0.016))
    assert not is_plausible_effect(Extraction(source_id="x", effect_type="OR", point=25.0))


def test_is_plausible_effect_none_point_passes():
    # Нет числа — не наше дело; отфильтруется дальше по `se`.
    assert is_plausible_effect(Extraction(source_id="x", effect_type="HR", point=None))


def test_is_plausible_effect_md_smd_not_gated():
    # Разностные меры — шкала исхода неизвестна на уровне stats, не режем.
    assert is_plausible_effect(Extraction(source_id="x", effect_type="MD", point=10.0))
    assert is_plausible_effect(Extraction(source_id="x", effect_type="SMD", point=-3.0))


def test_is_plausible_effect_rejects_nonfinite():
    assert not is_plausible_effect(Extraction(source_id="x", effect_type="HR", point=math.inf))
    assert not is_plausible_effect(Extraction(source_id="x", effect_type="HR", point=math.nan))
