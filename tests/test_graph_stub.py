"""E2E на заглушках (quality-gate P0/P1): граф гипотеза→отчёт проходит без сети."""

import asyncio

from src.app.main import DEMO_HYPOTHESIS, build_demo_deps, run, run_full
from src.domain.schemas import MetaResult


def test_pipeline_produces_report():
    report = asyncio.run(run(DEMO_HYPOTHESIS, build_demo_deps()))
    assert report.citations  # включённые источники прошли backbone
    assert report.confidence in ("high", "moderate", "low", "very_low")  # GRADE-уровень
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


def test_p2_extraction_and_pool():
    """Quality-gate P2: честная таблица эффектов + непустой пул на замороженном кейсе."""
    final = asyncio.run(run_full(DEMO_HYPOTHESIS, build_demo_deps()))
    assert final["pico"].is_complete()  # PICO извлечён через LLMPort

    extractions = final["extractions"]
    assert len(extractions) == 2  # два включённых РКИ
    assert all(e.variance_source == "reported_ci" for e in extractions)  # SE восстановлен из ДИ
    assert all(e.se and e.se > 0 for e in extractions)

    meta = final["meta"]
    assert isinstance(meta, MetaResult)
    assert meta.k_studies == 2
    assert 0.55 < meta.pooled_point < 0.66  # пул HR ~0.61, в пользу терапии
    assert meta.grade in ("high", "moderate", "low", "very_low")
    assert final["report"].direction == "favors_intervention"
