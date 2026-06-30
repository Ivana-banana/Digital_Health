"""Интерактивный драйвер графа для UI (plan §3, §12).

Тонкий слой между Streamlit-оболочкой и LangGraph: компиляция графа с
checkpointer (MemorySaver) и детект ожидающего interrupt по thread_id. Логика
тестируется headless (`tests/test_interactive_graph.py`); Streamlit-файл логики
не несёт. Резюмирование делает вызывающий код через `Command(resume=...)`.
"""

from __future__ import annotations

import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Interrupt

from src.pipeline.deps import Deps
from src.pipeline.graph import build_graph


def build_session_graph(deps: Deps):
    """Граф с MemorySaver для human-in-the-loop (interrupt/resume в одной сессии)."""
    return build_graph(deps, checkpointer=MemorySaver())


def new_thread_config(thread_id: str | None = None) -> dict:
    """Конфиг с уникальным `thread_id` — ключ резюмируемого состояния (plan §3)."""
    return {"configurable": {"thread_id": thread_id or uuid.uuid4().hex}}


def pending_interrupt(graph, config: dict) -> Interrupt | None:
    """Первый ожидающий interrupt (вопрос врачу) или None, если граф завершён."""
    snap = graph.get_state(config)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0]
    return None
