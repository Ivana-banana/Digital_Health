"""Юнит-тесты парсеров PubMed на фикстурах (без сети)."""

import asyncio
import json
from pathlib import Path

from src.adapters.search.pubmed import (
    PubMedAdapter,
    design_from_pub_types,
    parse_efetch_xml,
    parse_esearch,
)
from src.domain.schemas import StudyDesign
from src.obs.ratelimit import RateLimiter

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


def test_parse_efetch_extracts_nct_and_acronym():
    """Trial-level ID: NCT из DataBank + acronym через кураторскую мапу (plan §6.2)."""
    xml = (FIX / "efetch_sample.xml").read_text(encoding="utf-8")
    sources = parse_efetch_xml(xml)
    a = sources[0]
    assert a.nct_id == "NCT01584648"
    assert a.trial_acronym == "COMBI-d"


def test_parse_efetch_nct_fallback_from_abstract():
    """Fallback: NCT встречается только в тексте абстракта (нет DataBank-блока)."""
    xml = (FIX / "efetch_sample.xml").read_text(encoding="utf-8")
    b = parse_efetch_xml(xml)[1]
    assert b.nct_id == "NCT99999999"
    assert b.trial_acronym is None  # неизвестен курованной мапе — ок


def test_parse_efetch_flags_retraction():
    xml = (FIX / "efetch_sample.xml").read_text(encoding="utf-8")
    b = parse_efetch_xml(xml)[1]
    assert b.retracted
    assert b.design == StudyDesign.OBSERVATIONAL


def test_design_from_pub_types_priority():
    assert design_from_pub_types(["Review", "Meta-Analysis"]) == StudyDesign.META_ANALYSIS
    assert design_from_pub_types(["Journal Article"]) == StudyDesign.UNKNOWN


class _Resp:
    def __init__(self, *, json_data=None, text=""):
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class _FakeClient:
    """Мок httpx.AsyncClient: esearch фиксирован, efetch отдаёт тексты по очереди."""

    def __init__(self, es_json, efetch_texts):
        self._es = es_json
        self._efetch = list(efetch_texts)
        self.efetch_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        return _Resp(json_data=self._es)

    async def post(self, url, data=None):
        text = self._efetch[self.efetch_calls]
        self.efetch_calls += 1
        return _Resp(text=text)


def test_search_retries_efetch_on_transient_parse_error(monkeypatch):
    """NCBI отдал битый XML на первом efetch → ретрай → валидный ответ (live-надёжность)."""
    import httpx

    es_json = json.loads((FIX / "esearch_sample.json").read_text(encoding="utf-8"))
    good_xml = (FIX / "efetch_sample.xml").read_text(encoding="utf-8")
    fake = _FakeClient(es_json, ["<PubmedArticleSet><broken", good_xml])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake)

    adapter = PubMedAdapter(limiter=RateLimiter(1000.0))
    result = asyncio.run(adapter.search("melanoma", limit=10))
    assert fake.efetch_calls == 2  # первый битый → второй успешный
    assert len(result.sources) == 2
