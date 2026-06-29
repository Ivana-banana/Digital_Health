"""Тесты пулинга и GRADE (plan §8) — детерминированно."""

from src.domain.grade import grade_level
from src.domain.schemas import Extraction, Infeasible, MetaResult, StudyDesign
from src.stats.effect_conversions import derive_variance
from src.stats.meta import fixed_effect_pool


def _hr(point, lo, hi):
    return derive_variance(
        Extraction(
            source_id="s", effect_type="HR", point=point, ci_low=lo, ci_high=hi, outcome="OS"
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


def test_grade_rct_abstract_only_downgraded():
    g = grade_level([StudyDesign.RCT, StudyDesign.RCT], i_squared=0.0, ci_low=0.5, ci_high=0.73)
    assert g == "moderate"  # high − 1 (косвенность: абстракты)


def test_grade_observational_starts_low():
    g = grade_level(
        [StudyDesign.OBSERVATIONAL], i_squared=80.0, ci_low=0.5, ci_high=2.0, abstract_only=False
    )
    assert g in ("low", "very_low")
