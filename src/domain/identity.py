"""Резолюция идентичности и дедуп источников (plan §6.2).

Критично против двойного счёта в мета-анализе — методическая ошибка, видимая
клиническому судье. Порядок матча: DOI → PMID → PMCID → fuzzy(title+year).

В P0 — детерминированное ядро + reducer для `ResearchState.candidates`.
Fuzzy-матч (нормализация заголовка) намеренно простой; усилим в P1 с тестами.
"""

from __future__ import annotations

import re

from src.domain.schemas import Source


def normalize_doi(doi: str | None) -> str | None:
    """DOI к канону: lowercase, без URL-префикса и версии-суффикса."""
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


def _norm_title(title: str) -> str:
    """Грубая нормализация заголовка для fuzzy-ключа: только буквы/цифры в нижнем регистре."""
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def identity_key(s: Source) -> str:
    """Стабильный ключ идентичности по сильнейшему доступному ID, иначе fuzzy(title+year)."""
    doi = normalize_doi(s.doi)
    if doi:
        return f"doi:{doi}"
    if s.pmid:
        return f"pmid:{s.pmid.strip()}"
    if s.pmcid:
        return f"pmcid:{s.pmcid.strip()}"
    return f"fuzzy:{_norm_title(s.title)}:{s.year or ''}"


def identity_dedup_reducer(existing: list[Source], new: list[Source]) -> list[Source]:
    """LangGraph-reducer: добавляет новые источники, отбрасывая идентичные уже накопленным."""
    merged = list(existing)
    seen = {identity_key(s) for s in merged}
    for s in new:
        key = identity_key(s)
        if key not in seen:
            seen.add(key)
            merged.append(s)
    return merged
