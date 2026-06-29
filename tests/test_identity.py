"""Юнит-тесты резолюции идентичности и дедуп-reducer (против двойного счёта, §6.2)."""

from src.domain.identity import identity_dedup_reducer, identity_key, normalize_doi
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
