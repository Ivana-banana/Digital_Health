"""E2E на заглушках (quality-gate P0/P1): граф гипотеза→отчёт проходит без сети."""

import asyncio

from src.app.main import DEMO_HYPOTHESIS, build_demo_deps, run, run_full
from src.domain.schemas import Infeasible


def test_pipeline_produces_report():
    report = asyncio.run(run(DEMO_HYPOTHESIS, build_demo_deps()))
    assert report.citations  # хотя бы один источник прошёл backbone
    assert report.confidence == "low"
    assert "врач" in report.disclaimer


def test_p1_scoping_prisma_and_dedup():
    """Quality-gate P1: scoping-артефакт, PRISMA с причиной-ретракцией, trust проставлен."""
    final = asyncio.run(run_full(DEMO_HYPOTHESIS, build_demo_deps()))

    scoping = final["scoping"]
    assert scoping.total_candidates == 3
    assert scoping.by_design == {"rct": 2, "observational": 1}

    prisma = final["prisma"]
    assert prisma.included == 2  # ретрагированное наблюдательное исключено
    assert prisma.excluded_by_reason == {"retracted": 1}

    # QueryTranslation проброшен в запрос (крит. 2)
    assert final["queries"][0].translation
    # trust проставлен наукометрией; Q1-журнал → высокий балл
    nejm = next(s for s in final["candidates"] if s.journal == "New England Journal of Medicine")
    assert nejm.sjr_quartile == "Q1"
    assert nejm.trust_score and nejm.trust_score > 50


def test_single_study_meta_is_infeasible():
    """С одним canned-источником пул невозможен → структурное Infeasible (§8)."""
    deps = build_demo_deps()

    async def _run():
        from src.pipeline.graph import build_graph

        return await build_graph(deps).ainvoke({"raw_hypothesis": DEMO_HYPOTHESIS})

    final = asyncio.run(_run())
    assert isinstance(final["meta"], Infeasible)
    assert final["pico"].is_complete()  # PICO извлечён через LLMPort
