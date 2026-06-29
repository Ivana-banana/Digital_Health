"""Юнит-тесты eligibility-скрининга и PRISMA-причин (plan §6.3)."""

from src.domain.eligibility import EligibilityCriteria, PrismaTally, screen_source
from src.domain.schemas import PICO, Source, StudyDesign

PICO_DEMO = PICO(intervention="анти-PD-1", outcome="выживаемость")


def test_retracted_excluded():
    d = screen_source(Source(title="x", retracted=True), PICO_DEMO)
    assert not d.include and d.reason == "retracted"


def test_wrong_design_excluded():
    crit = EligibilityCriteria(allowed_designs={StudyDesign.RCT})
    d = screen_source(Source(title="x", design=StudyDesign.CASE_REPORT), PICO_DEMO, crit)
    assert not d.include and d.reason == "wrong_study_type"


def test_missing_intervention_term_excluded():
    crit = EligibilityCriteria(require_terms=True)
    s = Source(title="химиотерапия и выживаемость", design=StudyDesign.RCT)
    d = screen_source(s, PICO_DEMO, crit)
    assert not d.include and d.reason == "wrong_intervention"


def test_relevant_included_and_tally():
    crit = EligibilityCriteria(require_terms=True)
    s = Source(title="анти-PD-1 улучшает выживаемость", design=StudyDesign.RCT)
    d = screen_source(s, PICO_DEMO, crit)
    assert d.include and d.reason is None

    tally = PrismaTally()
    tally.add(screen_source(Source(title="x", retracted=True), PICO_DEMO))
    tally.add(d)
    assert tally.excluded_by_reason == {"retracted": 1}
