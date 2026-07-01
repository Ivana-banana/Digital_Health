"""Адаптер PubMed (E-utilities), реализует `SearchPort` (plan §6.1).

Чистые парсеры (`parse_esearch`, `parse_efetch_xml`) тестируются на фикстурах без
сети. Live-клиент (`PubMedAdapter.search`) делает esearch→efetch под token-bucket
(NCBI 10 rps с ключом). QueryTranslation от ESearch пробрасывается в результат.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from src.domain.schemas import Source, StudyDesign
from src.obs.ratelimit import RateLimiter
from src.ports import SearchResult

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

_NCT_RE = re.compile(r"\bNCT\d{8}\b")
# Кураторская мапа NCT → acronym: включается trial-collapse'ом; расширяется точечно.
_ACRONYMS_PATH = Path(__file__).resolve().parents[3] / "data" / "trial_acronyms.json"
try:
    _NCT_ACRONYMS: dict[str, str] = json.loads(_ACRONYMS_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    _NCT_ACRONYMS = {}

# Маппинг Publication Type → дизайн (детерминированная база; модель A уточняет, §7).
_PT_DESIGN: list[tuple[str, StudyDesign]] = [
    ("meta-analysis", StudyDesign.META_ANALYSIS),
    ("randomized controlled trial", StudyDesign.RCT),
    ("systematic review", StudyDesign.REVIEW),
    ("review", StudyDesign.REVIEW),
    ("observational study", StudyDesign.OBSERVATIONAL),
    ("comparative study", StudyDesign.NON_RANDOMIZED),
    ("case reports", StudyDesign.CASE_REPORT),
]


def design_from_pub_types(pub_types: list[str]) -> StudyDesign:
    """Грубая классификация дизайна по Publication Types (сильнейший матч)."""
    lowered = [p.lower() for p in pub_types]
    for needle, design in _PT_DESIGN:
        if any(needle in p for p in lowered):
            return design
    return StudyDesign.UNKNOWN


def parse_esearch(data: dict) -> tuple[list[str], str | None]:
    """Из JSON ESearch вернуть (список PMID, QueryTranslation)."""
    result = data.get("esearchresult", {})
    return result.get("idlist", []), result.get("querytranslation")


def _text(node: ET.Element | None) -> str | None:
    return node.text if node is not None and node.text else None


def parse_efetch_xml(xml: str) -> list[Source]:
    """Распарсить EFetch XML (PubmedArticleSet) в список `Source`."""
    root = ET.fromstring(xml)
    sources: list[Source] = []
    for art in root.findall(".//PubmedArticle"):
        cit = art.find("MedlineCitation")
        if cit is None:
            continue
        pmid = _text(cit.find("PMID"))
        article = cit.find("Article")
        title = _text(article.find("ArticleTitle")) if article is not None else None

        abstract_parts = [t.text for t in art.findall(".//Abstract/AbstractText") if t.text]
        abstract = " ".join(abstract_parts) or None

        journal = _text(art.find(".//Journal/Title"))
        year_text = _text(art.find(".//JournalIssue/PubDate/Year"))
        year = int(year_text) if year_text and year_text.isdigit() else None

        pub_types = [t.text for t in art.findall(".//PublicationType") if t.text]
        retracted = any("retract" in p.lower() for p in pub_types)

        doi = pmcid = None
        for aid in art.findall(".//ArticleId"):
            id_type = aid.get("IdType")
            if id_type == "doi":
                doi = aid.text
            elif id_type == "pmc":
                pmcid = aid.text

        # Trial-level ID: сначала явный ClinicalTrials.gov DataBank в MedlineCitation
        # (DataBankName — дочерний элемент), затем fallback — regex NCT\d{8} по абстракту.
        nct_id: str | None = None
        for db in art.findall(".//DataBankList/DataBank"):
            name = _text(db.find("DataBankName")) or ""
            if name.lower() != "clinicaltrials.gov":
                continue
            for acc in db.findall(".//AccessionNumber"):
                if acc.text and _NCT_RE.fullmatch(acc.text.strip()):
                    nct_id = acc.text.strip().upper()
                    break
            if nct_id:
                break
        if nct_id is None and abstract:
            match = _NCT_RE.search(abstract)
            if match:
                nct_id = match.group(0).upper()
        trial_acronym = _NCT_ACRONYMS.get(nct_id) if nct_id else None

        sources.append(
            Source(
                doi=doi,
                pmid=pmid,
                pmcid=pmcid,
                nct_id=nct_id,
                trial_acronym=trial_acronym,
                title=title or "",
                journal=journal,
                year=year,
                abstract=abstract,
                publication_types=pub_types,
                design=design_from_pub_types(pub_types),
                retracted=retracted,
            )
        )
    return sources


@dataclass
class PubMedAdapter:
    """Live-реализация `SearchPort` поверх NCBI E-utilities."""

    limiter: RateLimiter
    api_key: str | None = None
    timeout: float = 20.0

    def _params(self, **kw: str) -> dict[str, str]:
        params = {"db": "pubmed", **kw}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    async def search(self, query: str, *, limit: int = 100) -> SearchResult:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await self.limiter.acquire()
            es = await client.get(
                ESEARCH,
                params=self._params(term=query, retmax=str(limit), retmode="json"),
            )
            ids, translation = parse_esearch(es.json())
            if not ids:
                return SearchResult(sources=[], translation=translation)

            await self.limiter.acquire()
            ef = await client.post(
                EFETCH,
                data=self._params(id=",".join(ids), retmode="xml"),
            )
            return SearchResult(sources=parse_efetch_xml(ef.text), translation=translation)
