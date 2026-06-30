"""Query-planner (P5-фикс live-retrieval): запрос из PICO + фильтр РКИ для мета-пути.

Без фильтра типа исследования живой PubMed отдаёт обзоры/case-report (дизайн unknown,
0 пригодных эффектов). Запрос строится из P/I/O + RCT-фильтра; comparison не включаем
(сужает выдачу). Офлайн не затронут — FrozenSearch игнорирует текст запроса.
"""

import asyncio

from src.adapters.llm.stub import StubLLM
from src.domain.schemas import PICO
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
