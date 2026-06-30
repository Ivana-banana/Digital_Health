"""Офлайн-верификатор ссылок против замороженного корпуса (plan §9, §10).

Реализует `VerifierPort` без сети: ссылка подтверждена, если её идентификатор
есть среди реально найденных источников. Галлюцинированный DOI/PMID → не подтверждён.
Live-аналог (Crossref/PubMed) живёт за тем же портом.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CorpusVerifier:
    """`VerifierPort` поверх множества допустимых идентификаторов источников."""

    valid_ids: set[str]

    async def verify(self, source_id: str) -> bool:
        return source_id in self.valid_ids
