"""Юнит-тесты доменных схем (контракт `unavailable`, полнота PICO)."""

from src.domain.schemas import PICO, Extraction


def test_extraction_defaults_to_unavailable():
    """Контракт §0.2: дисперсия по умолчанию «не сообщено», а не выдуманное число."""
    e = Extraction(source_id="pmid:1")
    assert e.variance_source == "unavailable"
    assert e.point is None
    assert e.effect_type is None


def test_pico_completeness():
    assert not PICO(population="p", intervention="i").is_complete()
    assert PICO(population="p", intervention="i", comparison="c", outcome="o").is_complete()
