"""E2E на заглушках (quality-gate P0): граф гипотеза→отчёт проходит без сети."""

import asyncio

from src.app.main import DEMO_HYPOTHESIS, build_demo_deps, run
from src.domain.schemas import Infeasible


def test_pipeline_produces_report():
    report = asyncio.run(run(DEMO_HYPOTHESIS, build_demo_deps()))
    assert report.citations  # хотя бы один источник прошёл backbone
    assert report.confidence == "low"
    assert "врач" in report.disclaimer


def test_single_study_meta_is_infeasible():
    """С одним canned-источником пул невозможен → структурное Infeasible (§8)."""
    deps = build_demo_deps()

    async def _run():
        from src.pipeline.graph import build_graph

        return await build_graph(deps).ainvoke({"raw_hypothesis": DEMO_HYPOTHESIS})

    final = asyncio.run(_run())
    assert isinstance(final["meta"], Infeasible)
    assert final["pico"].is_complete()  # PICO извлечён через LLMPort
