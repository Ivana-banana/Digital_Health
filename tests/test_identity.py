"""Юнит-тесты резолюции идентичности и дедуп-reducer (против двойного счёта, §6.2)."""

from src.domain.identity import (
    collapse_by_trial,
    identity_dedup_reducer,
    identity_key,
    merge_sources,
    normalize_doi,
    trial_key,
)
from src.domain.schemas import Source


def test_normalize_doi_strips_prefix_and_case():
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi(None) is None


def test_doi_takes_priority_over_title():
    a = Source(doi="10.1/x", title="Different A")
    b = Source(doi="10.1/X", title="Different B")
    assert identity_key(a) == identity_key(b)


def test_reducer_dedups_same_identity():
    existing = [Source(pmid="1", title="A")]
    new = [Source(pmid="1", title="A dup"), Source(pmid="2", title="B")]
    merged = identity_dedup_reducer(existing, new)
    assert [s.pmid for s in merged] == ["1", "2"]


def test_cross_id_merge_via_shared_pmid():
    """PubMed-запись (pmid+doi) и OpenAlex-запись (только pmid) — одна публикация."""
    a = Source(pmid="1", doi="10.1/x", title="Trial")
    b = Source(pmid="1", citations=42)  # тот же PMID, без DOI
    merged = merge_sources([a, b])
    assert len(merged) == 1
    # дозаполнение: DOI из a, цитирования из b
    assert merged[0].doi == "10.1/x"
    assert merged[0].citations == 42


def test_merge_preserves_trial_identity_fields():
    # Регресс: nct_id/trial_acronym НЕ должны теряться при slii dedup через identity_dedup_reducer.
    a = Source(pmid="1", nct_id="NCT01597908", trial_acronym="COMBI-v")
    b = Source(pmid="1", citations=10)
    merged = merge_sources([a, b])
    assert len(merged) == 1
    assert merged[0].nct_id == "NCT01597908"
    assert merged[0].trial_acronym == "COMBI-v"


def test_distinct_sources_not_merged():
    a = Source(doi="10.1/a", title="A")
    b = Source(doi="10.1/b", title="B")
    assert len(merge_sources([a, b])) == 2


def test_fuzzy_merge_without_ids():
    a = Source(title="Anti-PD-1 in Melanoma!", year=2024)
    b = Source(title="anti pd 1 in melanoma", year=2024)
    assert len(merge_sources([a, b])) == 1


# --- Trial-level identity (plan §6.2) --------------------------------------------------------


def test_trial_key_prefers_nct_over_acronym():
    s = Source(pmid="1", nct_id="NCT01584648", trial_acronym="COMBI-d")
    assert trial_key(s) == "nct:NCT01584648"


def test_trial_key_falls_back_to_acronym():
    s = Source(pmid="1", trial_acronym="COMBI-v")
    assert trial_key(s) == "acronym:combi-v"


def test_trial_key_none_when_no_signal():
    assert trial_key(Source(pmid="1")) is None


def test_collapse_by_trial_common_nct_keeps_primary_os_report():
    # Первичная OS-публикация (HR+CI в абстракте) должна победить биомаркерный субанализ
    # того же трайла, даже если субанализ вышел позже (важно: HR+CI доминирует над годом).
    primary = Source(
        pmid="26037941",
        nct_id="NCT01584648",
        year=2015,
        abstract="Overall survival hazard ratio [HR] 0.71 (95% CI 0.55-0.92).",
    )
    later_subanalysis = Source(
        pmid="99999999",
        nct_id="NCT01584648",
        year=2019,
        abstract="Biomarker subgroup analysis: PD-L1 stratification.",
    )
    winners = collapse_by_trial([primary, later_subanalysis])
    assert winners == {identity_key(primary)}


def test_collapse_by_trial_acronym_only():
    a = Source(pmid="1", trial_acronym="COMBI-v", abstract="overall survival HR 0.69")
    b = Source(pmid="2", trial_acronym="COMBI-v", abstract="progression-free biomarker split")
    winners = collapse_by_trial([a, b])
    assert winners == {identity_key(a)}


def test_collapse_by_trial_passes_through_without_signal():
    # Без trial-сигналов каждый — сам себе трайл, никого не режем.
    a = Source(pmid="1", title="A")
    b = Source(pmid="2", title="B")
    winners = collapse_by_trial([a, b])
    assert winners == {identity_key(a), identity_key(b)}


def test_collapse_by_trial_distinct_trials_kept():
    a = Source(pmid="1", nct_id="NCT01584648", abstract="overall survival HR 0.71")
    b = Source(pmid="2", nct_id="NCT01597908", abstract="overall survival HR 0.69")
    winners = collapse_by_trial([a, b])
    assert winners == {identity_key(a), identity_key(b)}


def test_collapse_by_trial_empty_input():
    assert collapse_by_trial([]) == set()
