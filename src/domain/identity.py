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
        nct_id=a.nct_id or b.nct_id,
        trial_acronym=a.trial_acronym or b.trial_acronym,
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


# --- Trial-level identity (plan §6.2): множество публикаций одного РКИ → одна первичная. -----


def trial_key(s: Source) -> str | None:
    """Ключ трайла: NCT (сильный) → acronym (fallback). None — сигнала нет, каждый сам трайл."""
    if s.nct_id:
        return f"nct:{s.nct_id.strip().upper()}"
    if s.trial_acronym:
        return f"acronym:{s.trial_acronym.strip().lower()}"
    return None


_HR_CI_RE = re.compile(
    r"(hazard ratio|\bHR\b)[^.]{0,60}?(\(\s*(95\s*%?\s*)?CI|95\s*%\s*CI)",
    re.IGNORECASE,
)
_OS_RE = re.compile(r"overall survival|survival was", re.IGNORECASE)


def _has_os_hr_with_ci(text: str) -> bool:
    """OS-HR с CI в проксимити: HR/CI внутри ~300 символов от упоминания OS/death/mortality.

    Ловит паттерн «overall survival … HR 0.69 (95% CI 0.53–0.89)» и «hazard ratio for death,
    0.69; 95% CI, 0.53 to 0.89». Разбито на два условия (OS-контекст + отдельно HR+CI в
    проксимити), потому что regex-alternation с длинной дистанцией плохо матчит.
    """
    for m in _OS_RE.finditer(text):
        window = text[max(0, m.start() - 100) : m.end() + 300]
        if _HR_CI_RE.search(window):
            return True
    # Отдельно: «hazard ratio for death/mortality» — прямая формулировка OS-HR (COMBI-v-стиль).
    for m in re.finditer(r"hazard ratio for (death|mortality)", text, re.IGNORECASE):
        window = text[m.start() : m.end() + 300]
        if _HR_CI_RE.search(window) or re.search(r"95\s*%?\s*CI", window, re.IGNORECASE):
            return True
    return False


def _primary_os_score(s: Source) -> tuple[float, int]:
    """Эвристика первичной OS-публикации: доминирует явный **OS-HR с CI** в абстракте.

    OS-HR с CI (proximity к «overall survival» / «death» / «mortality») даёт 20 — доминирует.
    HR+CI где угодно (без OS-контекста) — 5 (может быть биомаркер / PFS). Так primary OS-report
    с полным HR+CI бьёт и follow-up без CI, и биомаркерный анализ. Тай-брейкер — РАННЯЯ
    публикация: interim OS обычно и есть та, что в Cochrane; поздние follow-up без CI проиграют
    первичной с полным HR+CI даже за счёт year, но при равенстве берём раннюю.
    """
    text = s.abstract or ""
    score = 0.0
    if _has_os_hr_with_ci(text):
        score += 20.0
    elif _HR_CI_RE.search(text):
        score += 5.0
    if _OS_RE.search(text):
        score += 2.0
    if s.year is not None:
        score += min(1.0, max(0.0, (s.year - 2000) / 30))
    # Тай-брейк по обратному PMID: при равном score берём РАННЮЮ публикацию (меньший PMID).
    # `max()` берёт наибольший `tiebreak`; `-pmid` инвертирует, поэтому побеждает `min(pmid)`.
    pmid_int = int(s.pmid) if s.pmid and s.pmid.isdigit() else 0
    return score, -pmid_int


def collapse_by_trial(sources: list[Source]) -> set[str]:
    """Из группы публикаций одного РКИ выбрать первичную OS-публикацию (одну на трайл-ключ).

    Возвращает set `identity_key(source)` победителей. Источники без trial-сигнала
    пропускаются (каждый — сам себе трайл). Пустой вход → пустой set.
    """
    groups: dict[str, list[Source]] = {}
    winners: set[str] = set()
    for s in sources:
        key = trial_key(s)
        if key is None:
            winners.add(identity_key(s))
        else:
            groups.setdefault(key, []).append(s)
    for _, group in groups.items():
        primary = max(group, key=_primary_os_score)
        winners.add(identity_key(primary))
    return winners
