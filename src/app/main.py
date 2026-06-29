"""Точка входа решения (контракт ИИ-судьи: `docker compose run --rm app`, plan §12).

Прогоняет canned-гипотезу через граф на offline-`StubLLM` + замороженном корпусе
(без сети/ключей, frozen-eval) и печатает ход исследования. Маркер `Solution started`
проверяют дымовой тест и агент-оценщик (см. DEPLOY.md).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.adapters.llm.stub import StubLLM
from src.adapters.scientometrics.scimago import ScimagoTable
from src.adapters.search.frozen import FrozenSearch
from src.domain.schemas import PICO, Extraction, MetaResult, Report
from src.pipeline.deps import Deps
from src.pipeline.graph import build_graph
from src.pipeline.state import ResearchState

ROOT = Path(__file__).resolve().parents[2]

# Canned-гипотеза и ожидаемый PICO для офлайн-демо (== единый замороженный корпус, plan §10).
DEMO_HYPOTHESIS = (
    "У пациентов с метастатической меланомой анти-PD-1 терапия "
    "улучшает общую выживаемость по сравнению с химиотерапией."
)
# PICO — на EN (язык поиска/извлечения, plan §6.1); вход врача и отчёт — RU.
DEMO_PICO = PICO(
    population="metastatic melanoma",
    intervention="anti-PD-1",
    comparison="chemotherapy",
    outcome="overall survival",
)


# Canned-извлечения в порядке кандидатов корпуса (HR из абстрактов NEJM/Lancet).
# Замороженный вход извлечения == источник истины для frozen-eval (plan §10).
DEMO_EXTRACTIONS = [
    Extraction(source_id="", effect_type="HR", point=0.58, ci_low=0.44, ci_high=0.77),
    Extraction(source_id="", effect_type="HR", point=0.63, ci_low=0.50, ci_high=0.80),
]


def build_demo_deps() -> Deps:
    """Deps для офлайн-демо: StubLLM + замороженный поиск + офлайн-квартили Scimago."""
    return Deps(
        llm=StubLLM(
            canned={"PICO": DEMO_PICO},
            canned_seq={"Extraction": [e.model_copy() for e in DEMO_EXTRACTIONS]},
        ),
        search=FrozenSearch.from_json(ROOT / "eval" / "frozen" / "corpus.json"),
        scimago=ScimagoTable.load(ROOT / "data" / "scimago_quartiles.csv"),
    )


async def run_full(hypothesis: str, deps: Deps) -> ResearchState:
    """Прогнать гипотезу через граф и вернуть финальное состояние."""
    graph = build_graph(deps)
    return await graph.ainvoke({"raw_hypothesis": hypothesis})


async def run(hypothesis: str, deps: Deps) -> Report:
    """Прогнать гипотезу через граф и вернуть отчёт."""
    final = await run_full(hypothesis, deps)
    return final.get("report") or Report()


def main() -> None:
    print("Solution started")
    final = asyncio.run(run_full(DEMO_HYPOTHESIS, build_demo_deps()))
    report = final.get("report") or Report()
    queries = final.get("queries") or []
    scoping = final.get("scoping")
    prisma = final.get("prisma")
    extractions = final.get("extractions") or []
    meta = final.get("meta")

    print(f"Гипотеза: {DEMO_HYPOTHESIS}")
    if queries and queries[0].translation:
        print(f"QueryTranslation: {queries[0].translation}")
    if scoping:
        print(f"Scoping: всего {scoping.total_candidates}, по дизайну {scoping.by_design}")
    if prisma:
        print(
            f"PRISMA: включено {prisma.included}, исключено {prisma.excluded} "
            f"{prisma.excluded_by_reason}"
        )
    if extractions:
        print("Извлечённые эффекты:")
        for e in extractions:
            ci = f"({e.ci_low}–{e.ci_high})" if e.ci_low else ""
            print(f"  - {e.source_id}: {e.effect_type} {e.point} {ci} [{e.variance_source}]")
    if isinstance(meta, MetaResult):
        print(
            f"Мета-анализ ({meta.model}, k={meta.k_studies}): {meta.effect_type} "
            f"{meta.pooled_point:.2f} (95% CI {meta.pooled_ci_low:.2f}–{meta.pooled_ci_high:.2f}), "
            f"I²={meta.i_squared}%"
        )
    print(f"Направление: {report.direction} | Доказательность (GRADE): {report.confidence}")
    print(report.disclaimer)


if __name__ == "__main__":
    main()
