"""Юнит-тесты trust-скоринга (plan §6.3)."""

from src.domain.schemas import Source, StudyDesign
from src.domain.scoring import trust_breakdown, trust_score


def test_rct_q1_recent_scores_high():
    s = Source(design=StudyDesign.RCT, sjr_quartile="Q1", citations=1000, year=2025)
    score = trust_score(s, current_year=2026)
    assert score > 70


def test_retraction_zeroes_score():
    s = Source(design=StudyDesign.RCT, sjr_quartile="Q1", citations=1000, year=2025, retracted=True)
    assert trust_score(s, current_year=2026) == 0.0


def test_breakdown_components_present():
    s = Source(design=StudyDesign.OBSERVATIONAL, sjr_quartile="Q3", citations=0, year=2010)
    bd = trust_breakdown(s, current_year=2026)
    assert bd["design"] == 18
    assert bd["quartile"] == 10
    assert bd["citation"] == 0.0
    assert bd["recency"] == 2.0  # старше 10 лет
