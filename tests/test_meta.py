"""Тесты пулинга и GRADE (plan §8) — детерминированно."""

import math

from src.domain.grade import grade_level
from src.domain.schemas import Appraisal, Extraction, Infeasible, MetaResult, StudyDesign
from src.stats.effect_conversions import derive_variance
from src.stats.meta import (
    egger_test,
    fixed_effect_pool,
    leave_one_out,
    random_effects_pool,
    sensitivity_by_rob,
)


def _study(point, se):
    """Исследование с заданным эффектом и SE (лог-пространство для HR)."""
    return Extraction(
        source_id="s",
        effect_type="HR",
        point=point,
        se=se,
        variance_source="reported_se",
        outcome="OS",
    )


def _hr(point, lo, hi, sid="s"):
    return derive_variance(
        Extraction(
            source_id=sid, effect_type="HR", point=point, ci_low=lo, ci_high=hi, outcome="OS"
        )
    )


def test_pool_two_hr_studies():
    res = fixed_effect_pool([_hr(0.58, 0.44, 0.77), _hr(0.63, 0.50, 0.80)])
    assert isinstance(res, MetaResult)
    assert res.k_studies == 2
    assert abs(res.pooled_point - 0.61) < 0.02  # обратно-дисперсионный пул
    assert res.pooled_ci_low < res.pooled_point < res.pooled_ci_high
    assert res.i_squared == 0.0  # согласованные оценки


def test_single_study_infeasible():
    res = fixed_effect_pool([_hr(0.58, 0.44, 0.77)])
    assert isinstance(res, Infeasible)


def test_incompatible_measures_not_mixed():
    hr = _hr(0.58, 0.44, 0.77)
    or_ = derive_variance(
        Extraction(
            source_id="o", effect_type="OR", point=0.5, ci_low=0.3, ci_high=0.8, outcome="OS"
        )
    )
    # одна HR + одна OR → ни одной группы из ≥2 → Infeasible
    assert isinstance(fixed_effect_pool([hr, or_]), Infeasible)


def test_unavailable_excluded_from_pool():
    good = _hr(0.58, 0.44, 0.77)
    bad = derive_variance(Extraction(source_id="b", effect_type="HR", point=0.7, outcome="OS"))
    assert bad.variance_source == "unavailable"
    assert isinstance(fixed_effect_pool([good, bad]), Infeasible)


def test_random_effects_hksj_wider_than_fixed():
    """Согласованные исследования: τ²≈0, точка как у fixed, но HKSJ при k=2 шире ДИ."""
    studies = [_hr(0.58, 0.44, 0.77), _hr(0.63, 0.50, 0.80)]
    fixed = fixed_effect_pool(studies)
    re = random_effects_pool(studies)
    assert isinstance(re, MetaResult) and isinstance(fixed, MetaResult)
    assert re.model == "random_hksj"
    assert re.tau_squared == 0.0
    assert abs(re.pooled_point - fixed.pooled_point) < 0.01
    fixed_w = fixed.pooled_ci_high - fixed.pooled_ci_low
    re_w = re.pooled_ci_high - re.pooled_ci_low
    assert re_w > fixed_w  # t(df=1)≈12.7 расширяет ДИ при малом k (plan §8, §13)


def test_random_effects_heterogeneous_tau_positive():
    """Разнонаправленные оценки → τ²>0 и I² высокий (DerSimonian–Laird)."""
    re = random_effects_pool([_hr(0.50, 0.40, 0.62), _hr(1.30, 1.05, 1.61)])
    assert isinstance(re, MetaResult)
    assert re.tau_squared and re.tau_squared > 0
    assert re.i_squared and re.i_squared > 50


def test_random_effects_single_infeasible():
    assert isinstance(random_effects_pool([_hr(0.58, 0.44, 0.77)]), Infeasible)


def test_egger_none_below_ten_studies():
    """Egger требует ≥10 исследований (plan §8) — иначе None."""
    studies = [_study(0.6, 0.1 + 0.02 * i) for i in range(9)]
    assert egger_test(studies) is None


def test_egger_detects_asymmetry():
    """Симметричная воронка → p высокий; асимметрия малых исследований → p низкий."""
    ses = [0.05 + 0.03 * i for i in range(10)]
    theta, eps = math.log(0.6), 0.5
    sym = [_study(math.exp(theta + eps * s * (-1) ** i), s) for i, s in enumerate(ses)]
    asym = [_study(math.exp(1.5 * s + theta + eps * s * (-1) ** i), s) for i, s in enumerate(ses)]
    p_sym, p_asym = egger_test(sym), egger_test(asym)
    assert p_sym is not None and p_asym is not None
    assert p_asym < 0.1  # выраженная асимметрия воронки (смещение публикаций)
    assert p_sym > 0.1  # симметричная воронка — смещение не выявлено


def test_leave_one_out_returns_k_results():
    """LOO при k≥3: по одному пере-пулу без каждого исследования, каждый из k−1."""
    studies = [_hr(0.58, 0.44, 0.77), _hr(0.63, 0.50, 0.80), _hr(0.70, 0.55, 0.89)]
    loo = leave_one_out(studies)
    assert len(loo) == 3
    assert all(isinstance(r, MetaResult) and r.k_studies == 2 for r in loo)


def test_leave_one_out_too_few_is_empty():
    assert leave_one_out([_hr(0.58, 0.44, 0.77), _hr(0.63, 0.50, 0.80)]) == []


def test_sensitivity_excludes_high_rob():
    """Исключение high-RoB исследования меняет пул (plan §8: подгруппа по RoB)."""
    studies = [_hr(0.58, 0.44, 0.77, "a"), _hr(0.63, 0.50, 0.80, "b"), _hr(1.5, 1.1, 2.0, "c")]
    full = random_effects_pool(studies)
    sens = sensitivity_by_rob(studies, [Appraisal(source_id="c", overall="high")])
    assert isinstance(full, MetaResult) and isinstance(sens, MetaResult)
    assert sens.k_studies == 2
    assert sens.pooled_point < full.pooled_point  # убрали неблагоприятное → сильнее за терапию


def test_grade_rct_abstract_only_downgraded():
    g = grade_level([StudyDesign.RCT, StudyDesign.RCT], i_squared=0.0, ci_low=0.5, ci_high=0.73)
    assert g == "moderate"  # high − 1 (косвенность: абстракты)


def test_grade_observational_starts_low():
    g = grade_level(
        [StudyDesign.OBSERVATIONAL], i_squared=80.0, ci_low=0.5, ci_high=2.0, abstract_only=False
    )
    assert g in ("low", "very_low")


def test_grade_downgraded_for_publication_bias():
    """Значимый Egger → понижение за публикационное смещение (plan §8)."""
    g = grade_level(
        [StudyDesign.RCT, StudyDesign.RCT],
        i_squared=0.0,
        ci_low=0.5,
        ci_high=0.7,
        abstract_only=False,
        egger_p=0.02,
    )
    assert g == "moderate"


def test_grade_downgraded_for_high_rob():
    """Большинство исследований high-RoB → понижение за риск смещения (plan §8)."""
    g = grade_level(
        [StudyDesign.RCT, StudyDesign.RCT],
        i_squared=0.0,
        ci_low=0.5,
        ci_high=0.7,
        abstract_only=False,
        high_rob=True,
    )
    assert g == "moderate"


def test_grade_no_downgrade_when_egger_none():
    g = grade_level(
        [StudyDesign.RCT, StudyDesign.RCT],
        i_squared=0.0,
        ci_low=0.5,
        ci_high=0.7,
        abstract_only=False,
        egger_p=None,
    )
    assert g == "high"
