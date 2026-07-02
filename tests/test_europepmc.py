"""Адаптер Europe PMC (plan §6.4): чистый JATS-парсер на фикстуре + деградация fetch."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.adapters.fulltext.europepmc import EuropePmcAdapter, parse_fulltext_xml
from src.domain.schemas import Source
from src.obs.ratelimit import RateLimiter

_FIXTURE = Path(__file__).parent / "fixtures" / "europepmc_fulltext.xml"


def test_parse_fulltext_extracts_body_with_os_hr():
    body = parse_fulltext_xml(_FIXTURE.read_text(encoding="utf-8"))
    assert "hazard ratio for death was 0.66" in body
    assert "randomly assigned" in body
    assert "Results" in body  # заголовки секций сохранены как параграфы


def test_parse_fulltext_no_body_returns_empty():
    assert parse_fulltext_xml("<article><front/></article>") == ""


def test_fetch_without_pmcid_returns_none():
    adapter = EuropePmcAdapter(limiter=RateLimiter(5.0))
    src = Source(pmid="123", pmcid=None, title="No OA full text")
    assert asyncio.run(adapter.fetch(src)) is None
