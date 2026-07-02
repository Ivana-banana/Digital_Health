"""Адаптер Europe PMC, реализует `FullTextPort` (plan §6.4).

Чистый парсер `parse_fulltext_xml` (JATS `<body>` → текст) тестируется на фикстуре без
сети. Live-клиент `EuropePmcAdapter.fetch` тянет OA-full-text по pmcid под token-bucket;
нет pmcid / не Open Access / not-200 → None (пайплайн деградирует на абстракт).
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from src.domain.schemas import Source
from src.obs.ratelimit import RateLimiter

REST = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def parse_fulltext_xml(xml: str) -> str:
    """Извлечь тело статьи (JATS `<body>`): заголовки секций и параграфы → текст.

    Параграфы разделяются пустой строкой — вход для `domain.fulltext.chunk_fulltext`.
    Пустая строка, если тела нет (только абстракт / не полный текст).
    """
    root = ET.fromstring(xml)
    body = root.find(".//body")
    if body is None:
        body = root.find(".//{*}body")
    if body is None:
        return ""
    parts: list[str] = []
    for el in body.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("p", "title"):
            text = "".join(el.itertext()).strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


@dataclass
class EuropePmcAdapter:
    """Live-реализация `FullTextPort` поверх Europe PMC REST (OA full-text XML)."""

    limiter: RateLimiter
    timeout: float = 20.0

    async def fetch(self, source: Source) -> str | None:
        if not source.pmcid:
            return None
        pmcid = source.pmcid.upper()
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"

        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await self.limiter.acquire()
            resp = await client.get(f"{REST}/{pmcid}/fullTextXML")
        if resp.status_code != 200:
            return None
        return parse_fulltext_xml(resp.text) or None
