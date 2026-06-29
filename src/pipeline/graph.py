"""Сборка LangGraph-графа (plan §3).

P0: линейная цепь backbone-узлов с reducer'ами состояния. `Deps` внедряются
через замыкание (узлы остаются (state, deps)-функциями). Ветвления, scoping-
interrupt и checkpointer добавляются в P1/P3.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from src.pipeline.deps import Deps
from src.pipeline.nodes import NODE_SEQUENCE
from src.pipeline.state import ResearchState


def build_graph(deps: Deps):
    """Скомпилировать граф гипотеза→отчёт с внедрёнными зависимостями."""
    builder = StateGraph(ResearchState)

    for name, fn in NODE_SEQUENCE:
        builder.add_node(name, partial(fn, deps=deps))

    builder.add_edge(START, NODE_SEQUENCE[0][0])
    for (prev, _), (nxt, _) in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:], strict=False):
        builder.add_edge(prev, nxt)
    builder.add_edge(NODE_SEQUENCE[-1][0], END)

    return builder.compile()
