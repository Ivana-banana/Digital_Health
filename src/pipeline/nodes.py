"""Узлы пайплайна (plan §3) — P0-заглушки.

Каждый узел возвращает частичный апдейт state (не мутирует его); списки
склеиваются reducer'ами. Логика детерминированная; узлы intake/synthesize
проходят через `LLMPort`, доказывая seam (структурный и текстовый исходы).
Реальная логика поиска/извлечения/мета приходит в P1–P3.
"""

from __future__ import annotations

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
    ScreenDecision,
    Source,
    StudyDesign,
)
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
    """Узел 3: поиск + identity-дедуп. Без SearchPort — один canned-источник."""
    if deps.search is not None:
        q = state["queries"][0].raw if state.get("queries") else state["raw_hypothesis"]
        candidates = await deps.search.search(q)
    else:
        candidates = [
            Source(
                pmid="00000000",
                title="Stub publication",
                journal="Journal of Stubs",
                year=2024,
                design=StudyDesign.RCT,
            )
        ]
    deps.logger.event("retrieve", found=len(candidates))
    return {"candidates": candidates, "audit": [Event(node="retrieve")]}


async def scientometrics(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 4: наукометрия + trust (заглушка — фиксируем событие)."""
    deps.logger.event("scientometrics", n=len(state.get("candidates", [])))
    return {"audit": [Event(node="scientometrics")]}


async def scoping(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 5: ScopingSummary — детерминированная агрегация над кандидатами."""
    candidates = state.get("candidates", [])
    by_design: dict[str, int] = {}
    for s in candidates:
        by_design[s.design.value] = by_design.get(s.design.value, 0) + 1
    summary = ScopingSummary(total_candidates=len(candidates), by_design=by_design)
    deps.logger.event("scoping", total=summary.total_candidates)
    return {"scoping": summary, "audit": [Event(node="scoping")]}


async def screen(state: ResearchState, deps: Deps) -> ResearchState:
    """Узел 6: eligibility → PRISMA. Заглушка включает всех кандидатов."""
    candidates = state.get("candidates", [])
    decisions = [ScreenDecision(source_id=identity_key(s), include=True) for s in candidates]
    prisma = PrismaCounts(
        identified=len(candidates),
        after_dedup=len(candidates),
        screened=len(candidates),
        included=len(candidates),
    )
    deps.logger.event("screen", included=prisma.included)
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
