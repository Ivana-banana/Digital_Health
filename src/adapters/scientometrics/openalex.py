"""Адаптер OpenAlex — цитируемость и venue за `ScientometricsPort` (plan §6.1).

Чистый `parse_openalex_works` тестируется на фикстуре. Live-`enrich` бьёт works
батчем по DOI/PMID под polite-pool (email). Источники не мутируются —
возвращаются копии с дозаполненными `citations`/`journal`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.identity import identity_tokens, normalize_doi
from src.domain.schemas import Source
from src.obs.ratelimit import RateLimiter

WORKS = "https://api.openalex.org/works"


@dataclass
class OAEnrichment:
    citations: int | None = None
    venue: str | None = None
    is_oa: bool = False


def _pmid_from_ids(ids: dict) -> str | None:
    raw = ids.get("pmid")
    if not raw:
        return None
    m = re.search(r"(\d+)$", raw)
    return m.group(1) if m else None


def parse_openalex_works(data: dict) -> dict[str, OAEnrichment]:
    """Из ответа OpenAlex построить карту {токен идентичности → обогащение}."""
    out: dict[str, OAEnrichment] = {}
    for w in data.get("results", []):
        ids = w.get("ids", {}) or {}
        doi = normalize_doi(w.get("doi"))
        pmid = _pmid_from_ids(ids)
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        enr = OAEnrichment(
            citations=w.get("cited_by_count"),
            venue=venue,
            is_oa=bool((w.get("open_access") or {}).get("is_oa")),
        )
        if doi:
            out[f"doi:{doi}"] = enr
        if pmid:
            out[f"pmid:{pmid}"] = enr
    return out


def apply_enrichment(sources: list[Source], table: dict[str, OAEnrichment]) -> list[Source]:
    """Наложить обогащение на источники по общим токенам идентичности (чистая функция)."""
    enriched: list[Source] = []
    for s in sources:
        match = next((table[t] for t in identity_tokens(s) if t in table), None)
        if match is None:
            enriched.append(s)
            continue
        enriched.append(
            s.model_copy(
                update={
                    "citations": s.citations if s.citations is not None else match.citations,
                    "journal": s.journal or match.venue,
                }
            )
        )
    return enriched


@dataclass
class OpenAlexAdapter:
    """Live-реализация `ScientometricsPort` поверх OpenAlex works."""

    limiter: RateLimiter
    email: str | None = None
    timeout: float = 20.0

    async def enrich(self, sources: list[Source]) -> list[Source]:
        import httpx

        dois = [normalize_doi(s.doi) for s in sources if s.doi]
        if not dois:
            return sources
        params = {"filter": "doi:" + "|".join(dois), "per-page": "200"}
        if self.email:
            params["mailto"] = self.email
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await self.limiter.acquire()
            resp = await client.get(WORKS, params=params)
        return apply_enrichment(sources, parse_openalex_works(resp.json()))
