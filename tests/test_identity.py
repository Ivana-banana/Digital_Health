"""Юнит-тесты резолюции идентичности и дедуп-reducer (против двойного счёта, §6.2)."""

from src.domain.identity import (
    identity_dedup_reducer,
    identity_key,
    merge_sources,
    normalize_doi,
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


def test_distinct_sources_not_merged():
    a = Source(doi="10.1/a", title="A")
    b = Source(doi="10.1/b", title="B")
    assert len(merge_sources([a, b])) == 2


def test_fuzzy_merge_without_ids():
    a = Source(title="Anti-PD-1 in Melanoma!", year=2024)
    b = Source(title="anti pd 1 in melanoma", year=2024)
    assert len(merge_sources([a, b])) == 1
