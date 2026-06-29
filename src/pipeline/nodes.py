"""Узлы пайплайна (plan §3).

Каждый узел возвращает частичный апдейт state (не мутирует его); списки
склеиваются reducer'ами. P1–P2 реализованы: retrieve (SearchPort+дедуп+QueryTranslation),
scientometrics (trust+квартиль), scoping, screen (eligibility→PRISMA), extract (LLM+
конверсии дисперсии), appraise (инструмент по дизайну), meta (fixed-effect пул+GRADE).
Synthesize/fact_check — базовые; полноценные гардрейлы и провенанс — P3.
"""

from __future__ import annotations

from src.domain.appraisal import appraise_baseline
from src.domain.eligibility import EligibilityCriteria, PrismaTally, screen_source
from src.domain.grade import grade_level
from src.domain.identity import identity_key
from src.domain.schemas import (
    PICO,
    Claim,
    Event,
    Extraction,
    MetaResult,
    PrismaCounts,
    Query,
    Report,
    ScopingSummary,
    Source,
    StudyDesign,
)
from src.domain.scoring import trust_score
from src.pipeline.deps import Deps
from src.pipeline.state import ResearchState
from src.ports import Ok
from src.stats.effect_conversions import derive_variance
from src.stats.meta import fixed_effect_pool, poolable

# Промпт извлечения: честная семантика «не сообщено» вместо догадки (plan §0.2, §9).
EXTRACT_SYS = (
    "Ты извлекаешь численный эффект из абстракта для заданного исхода. "
    "Верни СТРОГО JSON по схеме Extraction. effect_type — один из кодов: HR, OR, RR, MD, SMD "
    "(или null). Заполни point и, если есть, ci_low/ci_high или se; для 2×2 — events1/n_arm1/"
    "events2/n_arm2. Если эффект или его ДИ/SE не сообщены — effect_type=null и "
    "variance_source='unavailable'. Никогда не выдумывай числа. В evidence_span — дословная цитата."
)


async def sanitize(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 0: PII-скраб входа (заглушка) + событие аудита."""
    deps.logger.event("sanitize")
    return {"audit": [Event(node="sanitize")]}


async def intake_pico(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 1: структурирование гипотезы в PICO через LLM (структурный исход)."""
    res = await deps.llm.complete(
        [{"role": "user", "content": state["raw_hypothesis"]}],
        schema=PICO,
    )
    pico = res.value if isinstance(res, Ok) else PICO()
    deps.logger.event("intake_pico", complete=pico.is_complete())
    return {"pico": pico, "audit": [Event(node="intake_pico")]}


async def plan_queries(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 2: построение поискового запроса из PICO (заглушка — один запрос)."""
    pico = state.get("pico") or PICO()
    raw = " AND ".join(p for p in [pico.intervention, pico.outcome] if p) or state["raw_hypothesis"]
    deps.logger.event("plan_queries")
    return {"queries": [Query(source="pubmed", raw=raw)], "audit": [Event(node="plan_queries")]}


async def retrieve(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 3: поиск через `SearchPort` + identity-дедуп (reducer). QueryTranslation → запрос."""
    queries = state.get("queries", [])
    update: ResearchState = {"audit": [Event(node="retrieve")]}
    if deps.search is not None:
        q = queries[0].raw if queries else state["raw_hypothesis"]
        result = await deps.search.search(q, limit=deps.config.max_deep_studies * 5)
        update["candidates"] = result.sources
        if queries and result.translation:
            head = queries[0].model_copy(update={"translation": result.translation})
            update["queries"] = [head, *queries[1:]]
        deps.logger.event("retrieve", found=len(result.sources))
    else:
        update["candidates"] = [
            Source(
                pmid="00000000",
                title="Stub publication",
                journal="Journal of Stubs",
                year=2024,
                design=StudyDesign.RCT,
            )
        ]
        deps.logger.event("retrieve", found=1)
    return update


async def scientometrics(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 4: наукометрия (цитируемость/квартиль) + trust-скоринг. Влияет на порядок/GRADE."""
    candidates = state.get("candidates", [])
    if deps.scientometrics is not None:
        candidates = await deps.scientometrics.enrich(candidates)

    scored: list[Source] = []
    for c in candidates:
        upd: dict[str, object] = {}
        if deps.scimago is not None and (q := deps.scimago.quartile(c.journal)):
            upd["sjr_quartile"] = q
        c = c.model_copy(update=upd) if upd else c
        c = c.model_copy(
            update={"trust_score": trust_score(c, current_year=deps.config.current_year)}
        )
        scored.append(c)
    deps.logger.event("scientometrics", n=len(scored))
    return {"candidates": scored, "audit": [Event(node="scientometrics")]}


async def scoping(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 5: ScopingSummary — детерминированная агрегация над кандидатами (чекпойнт этапа-1)."""
    candidates = state.get("candidates", [])
    pico = state.get("pico")
    by_design: dict[str, int] = {}
    for s in candidates:
        by_design[s.design.value] = by_design.get(s.design.value, 0) + 1
    summary = ScopingSummary(
        total_candidates=len(candidates),
        by_design=by_design,
        outcomes=[pico.outcome] if pico and pico.outcome else [],
        populations=[pico.population] if pico and pico.population else [],
    )
    deps.logger.event("scoping", total=summary.total_candidates)
    return {"scoping": summary, "audit": [Event(node="scoping")]}


async def screen(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 6: детерминированный eligibility → PRISMA с причинами-enum (plan §6.3)."""
    candidates = state.get("candidates", [])
    pico = state.get("pico")
    criteria = EligibilityCriteria()  # ретракция отсекается всегда; типы/термины — за флагами
    tally = PrismaTally()
    decisions = []
    for s in candidates:
        d = screen_source(s, pico, criteria)
        decisions.append(d)
        tally.add(d)
    included = sum(1 for d in decisions if d.include)
    prisma = PrismaCounts(
        identified=len(candidates),
        after_dedup=len(candidates),
        screened=len(candidates),
        included=included,
        excluded=len(candidates) - included,
        excluded_by_reason=tally.excluded_by_reason,
    )
    deps.logger.event("screen", included=included, excluded=len(candidates) - included)
    return {"screening": decisions, "prisma": prisma, "audit": [Event(node="screen")]}


async def extract(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 7: извлечение эффектов LLM'ом (честный `unavailable`+span) → конверсии дисперсии."""
    pico = state.get("pico") or PICO()
    included = {d.source_id for d in state.get("screening", []) if d.include}
    candidates = [s for s in state.get("candidates", []) if identity_key(s) in included]
    # приоритизация top-N по trust (реранкер B — апгрейд за флагом, §6.4)
    candidates = sorted(candidates, key=lambda s: s.trust_score or 0, reverse=True)
    candidates = candidates[: deps.config.max_deep_studies]

    extractions: list[Extraction] = []
    for s in candidates:
        prompt = f"Исход: {pico.outcome}\nАбстракт: {s.abstract or ''}"
        res = await deps.llm.complete(
            [{"role": "system", "content": EXTRACT_SYS}, {"role": "user", "content": prompt}],
            schema=Extraction,
        )
        ex = res.value if isinstance(res, Ok) else Extraction(source_id=identity_key(s))
        ex = ex.model_copy(
            update={
                "source_id": identity_key(s),
                "design": s.design,
                "outcome": ex.outcome or pico.outcome or "",
                "text_source": "abstract",
            }
        )
        extractions.append(derive_variance(ex))  # дозаполнить SE / variance_source

    n_pool = sum(1 for e in extractions if e.variance_source != "unavailable")
    deps.logger.event("extract", n=len(extractions), poolable=n_pool)
    return {"extractions": extractions, "audit": [Event(node="extract")]}


async def appraise(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 8: критическая оценка качества — инструмент по дизайну + домены (plan §8)."""
    appraisals = [appraise_baseline(e.source_id, e.design) for e in state.get("extractions", [])]
    deps.logger.event("appraise", n=len(appraisals))
    return {"appraisals": appraisals, "audit": [Event(node="appraise")]}


async def meta(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 9: пул (fixed-effect IV) или структурное Infeasible; GRADE по доменам."""
    extractions = state.get("extractions", [])
    result = fixed_effect_pool(extractions)
    if isinstance(result, MetaResult):
        ps = poolable(extractions)
        result = result.model_copy(
            update={
                "grade": grade_level(
                    [e.design for e in ps],
                    i_squared=result.i_squared,
                    ci_low=result.pooled_ci_low,
                    ci_high=result.pooled_ci_high,
                    abstract_only=all(e.text_source == "abstract" for e in ps),
                )
            }
        )
    deps.logger.event("meta", feasible=isinstance(result, MetaResult))
    return {"meta": result, "audit": [Event(node="meta")]}


async def synthesize(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 10: отчёт. LLM даёт прозу (текстовый исход), сборка — детерминированная."""
    res = await deps.llm.complete(
        [{"role": "user", "content": "Summarize the evidence."}],
        schema=None,
        model_role="ru",
    )
    summary = res.content if hasattr(res, "content") else ""

    meta_res = state.get("meta")
    confidence = meta_res.grade if isinstance(meta_res, MetaResult) else "very_low"
    direction = None
    if isinstance(meta_res, MetaResult):
        point = meta_res.pooled_point
        direction = (
            "favors_intervention" if point < 1 else "favors_control" if point > 1 else "no_effect"
        )

    # цитируем только включённые исследования (provenance, §9)
    included = {d.source_id for d in state.get("screening", []) if d.include}
    citations = [
        s.pmid or s.doi or s.title
        for s in state.get("candidates", [])
        if identity_key(s) in included
    ]
    facts = [Claim(text=f"Включено исследований: {len(citations)}", type="fact", verified=False)]
    report = Report(
        summary=summary,
        direction=direction,
        confidence=confidence,
        facts=facts,
        citations=citations,
    )
    deps.logger.event("synthesize")
    return {"report": report, "provenance": facts, "audit": [Event(node="synthesize")]}


async def fact_check(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 11: гардрейл. Заглушка помечает факты verified (реальная верификация — P3)."""
    report = state.get("report")
    if report is not None:
        for c in report.facts:
            c.verified = True
    deps.logger.event("fact_check")
    return {"audit": [Event(node="fact_check")]}


# Порядок backbone (plan §3). В P0 — линейная цепь; ветвления/interrupt — P1/P3.
NODE_SEQUENCE = [
    ("sanitize", sanitize),
    ("intake_pico", intake_pico),
    ("plan_queries", plan_queries),
    ("retrieve", retrieve),
    ("scientometrics", scientometrics),
    ("scoping_review", scoping),
    ("screen", screen),
    ("extract", extract),
    ("appraise", appraise),
    ("meta_analysis", meta),
    ("synthesize", synthesize),
    ("fact_check", fact_check),
]
