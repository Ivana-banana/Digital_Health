"""Юнит-тесты парсеров PubMed на фикстурах (без сети)."""

import json
from pathlib import Path

from src.adapters.search.pubmed import (
    design_from_pub_types,
    parse_efetch_xml,
    parse_esearch,
)
from src.domain.schemas import StudyDesign

FIX = Path(__file__).parent / "fixtures"


def test_parse_esearch_ids_and_translation():
    data = json.loads((FIX / "esearch_sample.json").read_text(encoding="utf-8"))
    ids, translation = parse_esearch(data)
    assert ids == ["40000001", "40000002"]
    assert translation and "melanoma" in translation


def test_parse_efetch_extracts_fields():
    xml = (FIX / "efetch_sample.xml").read_text(encoding="utf-8")
    sources = parse_efetch_xml(xml)
    assert len(sources) == 2

    a = sources[0]
    assert a.pmid == "40000001"
    assert a.doi == "10.1056/nejmoa2024001"
    assert a.pmcid == "PMC9000001"
    assert a.year == 2024
    assert a.design == StudyDesign.RCT
    assert "HR 0.58" in (a.abstract or "")
    assert not a.retracted


def test_parse_efetch_flags_retraction():
    xml = (FIX / "efetch_sample.xml").read_text(encoding="utf-8")
    b = parse_efetch_xml(xml)[1]
    assert b.retracted
    assert b.design == StudyDesign.OBSERVATIONAL


def test_design_from_pub_types_priority():
    assert design_from_pub_types(["Review", "Meta-Analysis"]) == StudyDesign.META_ANALYSIS
    assert design_from_pub_types(["Journal Article"]) == StudyDesign.UNKNOWN
