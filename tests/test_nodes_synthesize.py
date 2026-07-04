"""synthesize: RU-резюме заземлено на детерминированные числа пула (анти-галлюцинация, §9).

Раньше узел просил LLM «сформулируй вывод» БЕЗ контекста — единственное место в проекте,
где свободный текст генерировался без заземления. Теперь в промпт уходят только посчитанные
числа пула, а при их отсутствии LLM не зовётся вовсе.
"""

from __future__ import annotations

import asyncio

from src.domain.schemas import (
    Extraction,
    Infeasible,
    MetaResult,
    ScreenDecision,
    Source,
    StudyDesign,
)
from src.pipeline.deps import Deps
from src.pipeline.nodes import synthesize
from src.ports import Text


class _CapturingLLM:
    """Fake LLMPort: записывает промпты; для schema=None отдаёт фиксированный текст."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, msgs, *, schema=None, temperature=0.0, model_role="workhorse"):
        self.calls.append(msgs)
        return Text("Пулированный эффект в пользу терапии.")


def _pool_state() -> dict:
    src = Source(pmid="1", title="Trial", design=StudyDesign.RCT)
    return {
        "screening": [ScreenDecision(source_id="pmid:1", include=True)],
        "candidates": [src],
        "extractions": [
            Extraction(
                source_id="pmid:1",
                effect_type="HR",
                point=0.70,
                se=0.08,
                variance_source="reported_ci",
                outcome="overall survival",
            )
        ],
        "meta": MetaResult(
            effect_type="HR",
            outcome="overall survival",
            k_studies=3,
            pooled_point=0.70,
            pooled_ci_low=0.59,
            pooled_ci_high=0.82,
            i_squared=0.0,
            grade="moderate",
        ),
    }


def test_summary_prompt_is_grounded_in_pool_numbers():
    llm = _CapturingLLM()
    out = asyncio.run(synthesize(_pool_state(), Deps(llm=llm)))

    assert len(llm.calls) == 1
    user_turn = llm.calls[0][-1]["content"]
    # Промпт несёт реальные числа пула, а не пустую просьбу «сформулируй вывод».
    assert "0.70" in user_turn
    assert "0.59" in user_turn and "0.82" in user_turn
    assert "3" in user_turn  # k_studies
    assert "moderate" in user_turn  # GRADE
    assert out["report"].summary  # непустое резюме


def test_summary_falls_back_to_deterministic_when_llm_empty():
    class _EmptyLLM:
        async def complete(self, msgs, *, schema=None, temperature=0.0, model_role="workhorse"):
            return Text("")

    out = asyncio.run(synthesize(_pool_state(), Deps(llm=_EmptyLLM())))
    summary = out["report"].summary
    # Пустой ответ LLM → детерминированный фолбэк с реальными числами, не пустота/выдумка.
    assert "0.70" in summary and "3" in summary


def test_infeasible_meta_uses_deterministic_message_without_llm_call():
    llm = _CapturingLLM()
    state = {
        "screening": [],
        "candidates": [],
        "extractions": [],
        "meta": Infeasible(reason="Нет исследований с извлекаемой дисперсией эффекта."),
    }
    out = asyncio.run(synthesize(state, Deps(llm=llm)))
    # При невозможной мете LLM не зовётся вовсе — нечего заземлять, нечего выдумывать.
    assert llm.calls == []
    assert out["report"].summary == "Доказательств недостаточно для вывода."
    assert out["report"].strength == "insufficient"
    assert out["report"].direction is None
