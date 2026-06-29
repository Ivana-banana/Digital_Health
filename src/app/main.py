"""Точка входа решения (контракт ИИ-судьи: `docker compose run --rm app`, plan §12).

P0: прогоняет canned-гипотезу через граф на offline-`StubLLM` (без сети/ключей,
frozen-eval) и печатает краткий отчёт. Печатает маркер `Solution started` —
его проверяют дымовой тест и агент-оценщик (см. DEPLOY.md).
"""

from __future__ import annotations

import asyncio

from src.adapters.llm.stub import StubLLM
from src.domain.schemas import PICO, Report
from src.pipeline.deps import Deps
from src.pipeline.graph import build_graph

# Canned-гипотеза и ожидаемый PICO для офлайн-демо (== единый замороженный корпус, plan §10).
DEMO_HYPOTHESIS = (
    "У пациентов с метастатической меланомой анти-PD-1 терапия "
    "улучшает общую выживаемость по сравнению с химиотерапией."
)
DEMO_PICO = PICO(
    population="метастатическая меланома",
    intervention="анти-PD-1",
    comparison="химиотерапия",
    outcome="общая выживаемость",
)


def build_demo_deps() -> Deps:
    """Deps для офлайн-демо: StubLLM с canned-PICO, остальные порты — None (деградация)."""
    return Deps(llm=StubLLM(canned={"PICO": DEMO_PICO}))


async def run(hypothesis: str, deps: Deps) -> Report:
    """Прогнать одну гипотезу через граф и вернуть отчёт."""
    graph = build_graph(deps)
    final = await graph.ainvoke({"raw_hypothesis": hypothesis})
    return final.get("report") or Report()


def main() -> None:
    print("Solution started")
    report = asyncio.run(run(DEMO_HYPOTHESIS, build_demo_deps()))
    print(f"Гипотеза: {DEMO_HYPOTHESIS}")
    print(f"Источников: {len(report.citations)}")
    print(f"Уровень доказательности: {report.confidence}")
    print(report.disclaimer)


if __name__ == "__main__":
    main()
