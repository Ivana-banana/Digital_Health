"""Узлы пайплайна (plan §3).

Каждый узел возвращает частичный апдейт state (не мутирует его); списки
склеиваются reducer'ами. P1 реализован: retrieve (SearchPort+дедуп+QueryTranslation),
scientometrics (trust+квартиль), scoping (артефакт этапа-1), screen (eligibility→PRISMA).
Извлечение эффектов, appraisal, мета-анализ и гардрейлы — заглушки до P2–P3.
"""

from __future__ import annotations

from src.domain.eligibility import EligibilityCriteria, PrismaTally, screen_source
from src.domain.identity import identity_key
from src.domain.schemas import (
    PICO,
    Appraisal,
    Claim,
    Event,
    Extraction,
    Infeasible,
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
    """Узел 7: извлечение эффектов. Заглушка — честный `unavailable` (не выдумка)."""
    included = {d.source_id for d in state.get("screening", []) if d.include}
    extractions = [
        Extraction(
            source_id=identity_key(s),
            design=s.design,
            outcome=(state.get("pico") or PICO()).outcome or "",
            variance_source="unavailable",
        )
        for s in state.get("candidates", [])
        if identity_key(s) in included
    ]
    deps.logger.event("extract", n=len(extractions))
    return {"extractions": extractions, "audit": [Event(node="extract")]}


async def appraise(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 8: критическая оценка качества (заглушка по доменам)."""
    appraisals = [
        Appraisal(source_id=e.source_id, tool="rob2", overall="some_concerns")
        for e in state.get("extractions", [])
    ]
    deps.logger.event("appraise", n=len(appraisals))
    return {"appraisals": appraisals, "audit": [Event(node="appraise")]}


async def meta(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 9: мета-gate. Заглушка: <2 совместимых эффектов → структурное Infeasible."""
    poolable = [e for e in state.get("extractions", []) if e.variance_source != "unavailable"]
    if len(poolable) >= 2:
        result: MetaResult | Infeasible = MetaResult(
            effect_type="HR",
            outcome=poolable[0].outcome,
            k_studies=len(poolable),
            pooled_point=1.0,
            pooled_ci_low=0.8,
            pooled_ci_high=1.25,
        )
    else:
        result = Infeasible(
            reason="Недостаточно исследований с извлекаемой дисперсией эффекта.",
            missing=["≥2 совместимых эффекта с ДИ/SE"],
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
    citations = [s.pmid or s.doi or s.title for s in state.get("candidates", [])]
    facts = [Claim(text=f"Найдено источников: {len(citations)}", type="fact", verified=False)]
    report = Report(
        summary=summary,
        direction=None,
        confidence="low",
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
