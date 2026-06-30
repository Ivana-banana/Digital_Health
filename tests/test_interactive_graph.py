"""Human-in-the-loop (quality-gate P4): interrupt() для PICO/scoping + резюм.

Headless-драйвер графа без Streamlit (UI-оболочка логики не несёт): проверяет оба
чекпойнта (plan §3), резюмирование по thread_id и гейтинг PICO-interrupt по полноте.
Проход насквозь при interactive=False покрыт `tests/test_graph_stub.py` (судья-контракт).
"""

import asyncio
from dataclasses import replace

from langgraph.types import Command

from src.adapters.llm.stub import StubLLM
from src.app.interactive import build_session_graph, new_thread_config, pending_interrupt
from src.app.main import DEMO_EXTRACTIONS, DEMO_HYPOTHESIS, build_demo_deps
from src.domain.schemas import PICO, Report


def _interactive_deps(pico: PICO):
    """Deps демо в интерактивном режиме с заданным (возможно неполным) PICO от LLM."""
    deps = build_demo_deps()
    deps.llm = StubLLM(
        canned={"PICO": pico},
        canned_seq={"Extraction": [e.model_copy() for e in DEMO_EXTRACTIONS]},
    )
    deps.config = replace(deps.config, interactive=True)
    return deps


async def _drive(deps, answers: dict):
    """Прогнать граф, отвечая на каждый interrupt по его типу; вернуть (типы, финал)."""
    graph = build_session_graph(deps)
    cfg = new_thread_config()
    seen: list[str] = []
    await graph.ainvoke({"raw_hypothesis": DEMO_HYPOTHESIS}, cfg)
    while (intr := pending_interrupt(graph, cfg)) is not None:
        seen.append(intr.value["type"])
        await graph.ainvoke(Command(resume=answers.get(intr.value["type"])), cfg)
    return seen, graph.get_state(cfg).values


def test_interrupts_pico_and_scoping_then_resume():
    """Неполный PICO → два чекпойнта (уточнение PICO + scoping) → резюм до отчёта."""
    incomplete = PICO(population="metastatic melanoma", intervention="anti-PD-1")
    answers = {
        "pico_clarification": {"comparison": "chemotherapy", "outcome": "overall survival"},
        "scoping_checkpoint": {"proceed": True},
    }
    seen, final = asyncio.run(_drive(_interactive_deps(incomplete), answers))

    assert seen == ["pico_clarification", "scoping_checkpoint"]
    assert final["pico"].is_complete()  # ответ врача дозаполнил недостающие грани
    assert final["pico"].comparison == "chemotherapy"
    report = final["report"]
    assert isinstance(report, Report)
    assert report.citations  # backbone дошёл до отчёта после резюма
    assert report.confidence in ("high", "moderate", "low", "very_low")


def test_complete_pico_skips_pico_interrupt():
    """Полный PICO → interrupt уточнения PICO не срабатывает, только scoping-чекпойнт."""
    complete = PICO(
        population="metastatic melanoma",
        intervention="anti-PD-1",
        comparison="chemotherapy",
        outcome="overall survival",
    )
    seen, final = asyncio.run(
        _drive(_interactive_deps(complete), {"scoping_checkpoint": {"proceed": True}})
    )

    assert seen == ["scoping_checkpoint"]  # PICO-interrupt пропущен (грани полны)
    assert isinstance(final["report"], Report)
