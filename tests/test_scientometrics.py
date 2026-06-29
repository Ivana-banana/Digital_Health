"""Юнит-тесты наукометрии: OpenAlex-парсер и Scimago-таблица (без сети)."""

import json
from pathlib import Path

from src.adapters.scientometrics.openalex import apply_enrichment, parse_openalex_works
from src.adapters.scientometrics.scimago import ScimagoTable
from src.domain.schemas import Source

FIX = Path(__file__).parent / "fixtures"


def test_openalex_parse_and_apply():
    data = json.loads((FIX / "openalex_sample.json").read_text(encoding="utf-8"))
    table = parse_openalex_works(data)
    # доступно и по DOI, и по PMID
    assert "doi:10.1056/nejmoa2024001" in table
    assert "pmid:40000001" in table

    src = Source(pmid="40000001", title="x")  # матч по PMID, DOI у нас нет
    enriched = apply_enrichment([src], table)
    assert enriched[0].citations == 137
    assert enriched[0].journal == "New England Journal of Medicine"


def test_openalex_no_match_leaves_source():
    table = {}
    src = Source(pmid="999", title="x")
    assert apply_enrichment([src], table)[0] is src


def test_scimago_quartile_lookup():
    table = ScimagoTable.load(FIX / "scimago_sample.csv")
    assert table.quartile("New England Journal of Medicine") == "Q1"
    assert table.quartile("new england journal of medicine") == "Q1"  # нормализация
    assert table.quartile("Unranked Newsletter") is None  # квартиль '-'
    assert table.quartile("Unknown Journal") is None
