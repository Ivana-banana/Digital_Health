"""Сборка LangGraph-графа (plan §3).

Линейная цепь backbone-узлов с reducer'ами + одно условное ребро (fact-check).
`Deps` внедряются через замыкание (узлы остаются (state, deps)-функциями). Для
human-in-the-loop (interrupt() в intake/scoping, plan §3) передаётся checkpointer —
без него граф идёт насквозь (офлайн/судья-режим), с ним пауза резюмируется по thread_id.
"""

from __future__ import annotations

from functools import partial

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from src.pipeline.deps import Deps
from src.pipeline.nodes import NODE_SEQUENCE, route_after_factcheck
from src.pipeline.state import ResearchState


def build_graph(deps: Deps, *, checkpointer: BaseCheckpointSaver | None = None):
    """Скомпилировать граф гипотеза→отчёт с внедрёнными зависимостями.

    `checkpointer` нужен только для интерактивного режима (interrupt/resume); по
    умолчанию None → backbone проходит насквозь (контракт ИИ-судьи неизменен).
    """
    builder = StateGraph(ResearchState)

    for name, fn in NODE_SEQUENCE:
        builder.add_node(name, partial(fn, deps=deps))

    builder.add_edge(START, NODE_SEQUENCE[0][0])
    for (prev, _), (nxt, _) in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:], strict=False):
        builder.add_edge(prev, nxt)
    # Гардрейл fact-check: регенерация секции (retry≤2) или конец (plan §3, §9).
    builder.add_conditional_edges(
        NODE_SEQUENCE[-1][0], route_after_factcheck, {"synthesize": "synthesize", END: END}
    )

    return builder.compile(checkpointer=checkpointer)
