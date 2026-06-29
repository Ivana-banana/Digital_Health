"""Тесты выбора инструмента оценки качества по дизайну (plan §8)."""

from src.domain.appraisal import appraise_baseline, tool_for
from src.domain.schemas import StudyDesign


def test_tool_selection_by_design():
    assert tool_for(StudyDesign.RCT) == "rob2"
    assert tool_for(StudyDesign.NON_RANDOMIZED) == "robins_i"
    assert tool_for(StudyDesign.OBSERVATIONAL) == "strobe"
    assert tool_for(StudyDesign.UNKNOWN) == "rob2"  # дефолт


def test_baseline_domains_unassessed():
    a = appraise_baseline("pmid:1", StudyDesign.RCT)
    assert a.tool == "rob2"
    assert set(a.domain_judgements) == {
        "randomization",
        "deviations",
        "missing_data",
        "measurement",
        "selection_of_result",
    }
    # честно: ничего ещё не оценено детально
    assert all(v == "unclear" for v in a.domain_judgements.values())
