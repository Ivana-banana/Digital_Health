"""Query-planner (P5-фикс live-retrieval): запрос из PICO + фильтр РКИ для мета-пути.

Без фильтра типа исследования живой PubMed отдаёт обзоры/case-report (дизайн unknown,
0 пригодных эффектов). Запрос строится из P/I/O + RCT-фильтра; comparison не включаем
(сужает выдачу). Офлайн не затронут — FrozenSearch игнорирует текст запроса.
"""

import asyncio

from src.adapters.llm.stub import StubLLM
from src.domain.schemas import PICO, QueryTerms
from src.pipeline.config import PipelineConfig
from src.pipeline.deps import Deps
from src.pipeline.nodes import plan_queries


def test_query_includes_pico_terms_and_rct_filter():
    state = {
        "raw_hypothesis": "гипотеза",
        "pico": PICO(
            population="metastatic melanoma",
            intervention="anti-PD-1",
            comparison="chemotherapy",
            outcome="overall survival",
        ),
    }
    q = asyncio.run(plan_queries(state, Deps(llm=StubLLM())))["queries"][0].raw

    assert "(metastatic melanoma)" in q
    assert "(anti-PD-1)" in q
    assert "(overall survival)" in q
    assert "randomized controlled trial[pt]" in q
    assert "chemotherapy" not in q  # comparison не сужает запрос


def test_query_falls_back_to_hypothesis_without_pico():
    state = {"raw_hypothesis": "free text hypothesis", "pico": PICO()}
    q = asyncio.run(plan_queries(state, Deps(llm=StubLLM())))["queries"][0].raw
    assert q == "free text hypothesis"  # нет граней PICO → без [pt]-фильтра по сырому тексту


def test_live_expansion_builds_query_from_drug_terms():
    # За флагом enable_query_expansion LLM раскрывает PICO в конкретные термины (live retrieval).
    state = {
        "raw_hypothesis": "гипотеза",
        "pico": PICO(
            population="BRAF V600-mutant melanoma",
            intervention="BRAF + MEK inhibitor",
            comparison="BRAF inhibitor monotherapy",
            outcome="overall survival",
        ),
    }
    llm = StubLLM(
        canned={
            "QueryTerms": QueryTerms(
                population_terms=["melanoma"],
                intervention_terms=["dabrafenib", "trametinib", "vemurafenib"],
                outcome_terms=["overall survival"],
            )
        }
    )
    deps = Deps(llm=llm, config=PipelineConfig(enable_query_expansion=True))
    q = asyncio.run(plan_queries(state, deps))["queries"][0].raw

    assert "(melanoma)" in q
    assert "(dabrafenib OR trametinib OR vemurafenib)" in q
    assert "(overall survival)" in q
    assert "randomized controlled trial[pt]" in q
    assert "BRAF + MEK inhibitor" not in q  # verbose-концепт заменён конкретикой


def test_expansion_off_keeps_mechanical_query():
    state = {
        "raw_hypothesis": "гипотеза",
        "pico": PICO(population="metastatic melanoma", intervention="anti-PD-1"),
    }
    # Флаг выключен → мех. запрос из самих граней PICO, LLM не зовётся.
    deps = Deps(llm=StubLLM(canned={"QueryTerms": QueryTerms(population_terms=["x"])}))
    q = asyncio.run(plan_queries(state, deps))["queries"][0].raw
    assert "(metastatic melanoma)" in q
    assert "(anti-PD-1)" in q
