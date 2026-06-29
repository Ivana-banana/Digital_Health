"""Резолюция идентичности и дедуп источников (plan §6.2).

Критично против двойного счёта в мета-анализе — методическая ошибка, видимая
клиническому судье. Две записи — одна публикация, если делят ЛЮБОЙ идентификатор
(DOI/PMID/PMCID) либо, при отсутствии сильных ID, fuzzy(title+year). Кластеризация
union-merge'ом склеивает запись из PubMed и ту же из OpenAlex и дозаполняет ID.
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


def identity_tokens(s: Source) -> set[str]:
    """Идентификаторы записи. Если сильных ID нет — fuzzy-ключ по заголовку+году."""
    toks: set[str] = set()
    doi = normalize_doi(s.doi)
    if doi:
        toks.add(f"doi:{doi}")
    if s.pmid:
        toks.add(f"pmid:{s.pmid.strip()}")
    if s.pmcid:
        toks.add(f"pmcid:{s.pmcid.strip()}")
    if not toks:
        toks.add(f"fuzzy:{_norm_title(s.title)}:{s.year or ''}")
    return toks


def identity_key(s: Source) -> str:
    """Стабильный одиночный ключ по сильнейшему ID, иначе fuzzy(title+year)."""
    doi = normalize_doi(s.doi)
    if doi:
        return f"doi:{doi}"
    if s.pmid:
        return f"pmid:{s.pmid.strip()}"
    if s.pmcid:
        return f"pmcid:{s.pmcid.strip()}"
    return f"fuzzy:{_norm_title(s.title)}:{s.year or ''}"


def _merge_two(a: Source, b: Source) -> Source:
    """Слить две записи об одной публикации: непустое поле важнее пустого."""
    return Source(
        doi=a.doi or b.doi,
        pmid=a.pmid or b.pmid,
        pmcid=a.pmcid or b.pmcid,
        title=a.title or b.title,
        journal=a.journal or b.journal,
        year=a.year or b.year,
        abstract=a.abstract or b.abstract,
        publication_types=sorted(set(a.publication_types) | set(b.publication_types)),
        design=a.design if a.design.value != "unknown" else b.design,
        citations=max([c for c in (a.citations, b.citations) if c is not None], default=None),
        sjr_quartile=a.sjr_quartile or b.sjr_quartile,
        retracted=a.retracted or b.retracted,
        trust_score=a.trust_score if a.trust_score is not None else b.trust_score,
    )


def merge_sources(sources: list[Source]) -> list[Source]:
    """Склеить дубликаты по общим идентификаторам, сохраняя порядок первого появления."""
    reps: list[Source | None] = []
    token_to_cluster: dict[str, int] = {}

    for s in sources:
        toks = identity_tokens(s)
        hit = {token_to_cluster[t] for t in toks if t in token_to_cluster}
        if not hit:
            idx = len(reps)
            reps.append(s)
            for t in toks:
                token_to_cluster[t] = idx
            continue

        target = min(hit)
        rep = reps[target]
        assert rep is not None
        rep = _merge_two(rep, s)
        for h in hit:
            if h != target and reps[h] is not None:
                rep = _merge_two(rep, reps[h])  # type: ignore[arg-type]
                reps[h] = None
        reps[target] = rep
        # перенаправить все токены поглощённых кластеров и новой записи на target
        for t, c in list(token_to_cluster.items()):
            if c in hit:
                token_to_cluster[t] = target
        for t in identity_tokens(rep) | toks:
            token_to_cluster[t] = target

    return [r for r in reps if r is not None]


def identity_dedup_reducer(existing: list[Source], new: list[Source]) -> list[Source]:
    """LangGraph-reducer: объединяет накопленные и новые источники без двойного счёта."""
    return merge_sources(existing + new)
